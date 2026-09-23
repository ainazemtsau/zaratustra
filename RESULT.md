# Core v0.1 Stage 5 pass 1 — durable subject continuation

## outcome

The owner approved pass 1 of `docs/core-v0.1/STAGE5-PLAN.md` from exact commit
`e29bc0450ce4ee6c67e5e28859c8e410a82f1771`. An explicit additive schema 4
now stores addressed independent Attempt assignments, questions/answers,
remainders, stop state and pending/cancelled outbox entries in the independent
foundation. They use the existing operation/audit/receipt transaction and current
rights. No Pi RPC, DBOS runner or dispatcher was introduced. The accepted
interactive Stage 4 bridge and direct execution API also admit schema 4, while
schema 3 spaces remain readable and usable without automatic upgrade.

## evidence

`docs/core-v0.1/STAGE5-IMPLEMENTATION.md` records the public surface and
maintenance boundary. Seven focused synthetic tests pass. One test reopens the
space in a new Python process, reads the durable question and remainder, saves
the answer and proves one `resume` outbox entry; exact replay does not create a
second. The others exercise explicit upgrade and Stage 4 bridge compatibility,
replay rights, revoked answer rights, stop/unknown reserve, stale Attempt fencing,
backup/quarantine/epoch and Work/Artifact deletion. The full
`uv run --locked python -m tools.check --deliver` passed with the verified SQLite
runtime: 181 format-clean files, clean Ruff, strict mypy on 155 source files,
21 kept import contracts, 495 passed tests, source/wheel build and report
structure. Independent review identified that a responder could create an
answer without the `receipt.read` right needed to replay its receipt after a
lost acknowledgement. Admission now requires this current right; a focused
test covers refusal without it and exact retry with it. This check is
engineering evidence, not owner acceptance.

## assumptions

The first pass records a pinned future executor version but never starts that
executor. An assignment and launch outbox item are durable intentions, not proof
of a live Pi child or external effect. The current Work stays `proposed` until
separate acceptance; actual `ready/running/waiting` Work transitions require
the next pass with observable process outcomes.

## cuts

No real model call, personal data, Pi RPC, DBOS production dependency, custom
dispatcher, old `.zara` migration, Direction OS change or
`C:\projects\zaratustra` change. Outbox delivery, live process ownership and
two-database maintenance remain for separately authorized later passes.

## cost

Local source, synthetic tests and documentation only; zero model/service calls
and zero paid cost.

## manual-acceptance

The owner authorized implementation and local delivery of pass 1. Focused and
full engineering checks are evidence, not owner acceptance of the completed
pass. The earlier Stage 4 owner acceptance remains separate.

## next

solmax

# Core v0.1 Stage 5 plan and Stage 4 owner acceptance

## outcome

The owner explicitly accepted the whole Stage 4 implementation at
`afa367c10ad949b1610810d4f2e6f106c1a7b7cc`, independently of the earlier
acceptance of one synthetic Work. `docs/core-v0.1/STAGE4-ACCEPTANCE.md` records
the exact words and scope. `docs/core-v0.1/STAGE5-PLAN.md` defines the next
minimal path: a separately assigned ordinary Pi RPC Attempt with a durable
question/answer, Core-owned state, DBOS-backed technical continuation subject
to an explicit backend decision, and recovery/maintenance gates. Stage 5 was
not implemented or executed in this planning pass.

## evidence

The specification SHA-256 was rechecked as
`1DDCBF9DBFD58426781F61A67A170D3CE85FCD2BA27B17549773ED3356F9428D`.
The Stage 4 HEAD was verified as
`afa367c10ad949b1610810d4f2e6f106c1a7b7cc` on `codex/core-v0.1`.
The plan was compared with the implementation/technical baselines, Stage 4
plan and implementation, scenario 9 machine report, RESULT history, and the
current public `foundation`/`pi_adapter` surfaces. `git diff --check` passed;
all referenced local files exist. The full
`uv run --locked python -m tools.check --deliver` passed with an isolated uv
cache and the previously verified SQLite runtime: 180 format-clean files,
clean Ruff, strict mypy on 154 files, 21 import contracts, 488 tests, source
and wheel build, and report structure. The default and reused uv caches were
inaccessible in this sandbox; the isolated cache resolved that setup error.

## assumptions

The first Stage 5 scenario uses one existing method-less Work and a fictional
read-only resource. DBOS 3.0.0 is the recommended conditional integration
candidate after its positive synthetic scenario 9; production suitability
still needs the real composition checks and an owner decision.

## cuts

No production code, DBOS production dependency, independent execution,
model call, personal data, old `.zara` migration, Direction OS edit, or
`C:\projects\zaratustra` edit is part of this pass. The full accepted Core
composition remains future work as detailed in the plan.

## cost

Documentation and local checks only; zero model/service calls and no paid cost.

## manual-acceptance

Stage 4 is accepted by the owner's explicit words; the synthetic Work was
accepted separately. This planning pass does not accept Stage 5 or approve its
production backend, model, resource or real data.

## next

solmax

# Core v0.1 Stage 4 proposed-output regeneration correction

## outcome

A new explicitly started Attempt on the current revision of a proposed Work
can replace an occupied output slot after an answered invocation. Core still
checks the exact Attempt basis and writes the Artifact and Work link in one
transaction. Earlier Artifacts and Work revisions remain readable. A Work
changed after Attempt start rejects late publication; `succeeded` remains
closed to new Attempts.

## evidence

The new synthetic regression failed before the fix at the unconditional
occupied-slot `stale_work` check. After the fix, it published a second answer
at Work@3, retained Work@2 and both exact Artifact payloads, kept one link for
the slot, replayed both publications exactly and explicitly accepted only the
new revision. The existing competing-link, deletion and acceptance checks
also passed in the focused 15-test run. The first full delivery run
reported 487 passed and one unrelated intermittent catalog concurrency failure
(`test_relocation_preserves_concurrently_added_independent_row`); that test
passed alone. The repeated full `tools.check --deliver` passed: 488 tests,
180 format-clean files, clean Ruff, strict mypy on 154 files, 21 import
contracts, source/wheel build and report structure.

## assumptions

A revised result requires an explicit new Attempt begun at the current
`proposed` Work revision. Operation replay uses the saved receipt before any
current-state validation, so a prior successful publication remains replayable.

## cuts

The correction changes only interactive Stage 4 publication. It adds no
executor, DBOS integration or model/provider contract.

## cost

Synthetic local tests only; zero real model calls and zero paid API calls in
this correction. The earlier owner-run synthetic Work used 953 reported units,
zero held after its answered call.

## manual-acceptance

The owner already accepted the earlier synthetic Work: revision 3 is
`succeeded`, with its explicit basis, original Artifact, 953 committed units,
zero held and no active Attempt. This does not constitute owner acceptance of
the full Stage 4 implementation. No repeat acceptance is requested.

## next

solmax

# Core v0.1 Stage 4 restart and acceptance correction

## outcome

The owner's synthetic manual test confirmed the saved Artifact, current rights
and 953 units in a fresh Pi session. That session also exposed an unwanted
empty active Attempt on a proposed Work with a linked output. The adapter now
opens that Work for reading without starting an Attempt. Explicit acceptance
retires any active Attempt in the same Core transaction under `work.accept`.
The owner's Work
remains `proposed`; no acceptance was performed by engineering.

## evidence

The fresh status showed the same Work@2, output Artifact, one answered
`openai-codex/gpt-5.6-luna` SSE invocation, 953 committed units and zero held.
It also showed a second active Attempt with no invocations. That exact empty
synthetic Attempt was interrupted through the public Core operation; the Work,
output, invocation count and accounting remained intact. Focused regression
checks cover acceptance with an active Attempt by an actor without
`work.execute` and its retirement. The full
`tools.check --deliver` passed: 487 tests, 21 import contracts, strict typing,
hygiene and source/wheel build.

## assumptions

An already linked proposed result is available for review after restart.
Starting another Attempt for revision remains an explicit `/zara-work` action.

## cuts

The ordinary Pi model loop and provider admission boundary are unchanged.
No next-stage executor or DBOS work was started.

## cost

The owner sent one additional subscribed Codex request against the synthetic
note: 953 reported units, zero held after its answer. Engineering sent no
model request in this follow-up. Total real subscribed sends across Stage 4
are now three; no paid API was used.

## manual-acceptance

The synthetic result is ready for the owner's own review and optional explicit
`/zara-accept`. Engineering did not accept it. After acceptance, inspect
`/zara-status` for `succeeded`, a basis and no active Attempt.

## next

solmax

# Core v0.1 Stage 4 correction

## outcome

Three reproduced Stage 4 defects are corrected in the local interactive path.
An unsupported Pi provider now stops before HTTP while a Work is selected.
Attempt publication checks its basis and links its Artifact in one Core
transaction, preserving a newer output. Adapter-created Pi session histories
are now managed in the selected Core space and retired during deletion
maintenance. The Work's successful result still requires a separate explicit
acceptance. No DBOS or independent RPC executor was added.

## evidence

Before editing, synthetic reproductions showed one unreserved HTTP request
after Pi switched to a second localhost provider; a late Attempt replaced a
different Work@2 output; and a Pi JSONL copy retained `fictional note` after
Work deletion. After the changes, the same ordinary Pi `set_model` switch made
zero provider requests and exposed no Core input. Focused tests prove a late
Attempt gets `stale_work`, leaves Work@2 and its exact bytes intact, creates no
late Artifact, and preserves exact publication replay. A synthetic managed
Pi JSONL file is removed by `complete_deletions`; maintenance refuses to run
while Pi owns the space. A supported localhost Pi run still made one observed
and admitted call, saved the output, and left Work proposed before its
synthetic-only acceptance step. The manual setup helper created a fresh
proposed synthetic Work in ignored `_scratch`.

The full `uv run --locked python -m tools.check --deliver` passed after the
core fixes. The final run checked 180 formatted files, clean Ruff, strict
mypy on 154 files, 21 import contracts, 486 tests, source/wheel build and
report structure.

## assumptions

The host has exclusive local ownership of the Core space while Pi runs.
Every host-created session is stored below `<space>/.zara-core/pi-sessions`;
deletion retires all such sessions because one transcript may mix material
from several Works. The same lock prevents concurrent Pi writes and cleanup.
Provider coverage is the ordinary Pi provider stream path used by this adapter.

## cuts

Historical Pi sessions created before this correction in arbitrary directories
cannot be discovered from Core because their paths were never recorded. They
need separate operator review and removal. Provider-side copies, manually
exported chats and filesystem snapshots are outside local Core maintenance.
Automatic publication remains limited to one textual output slot. No new
model/provider allowlist or fixed product budget was introduced.

## cost

Zero real model calls and zero paid API calls in this correction. All model
transport checks used synthetic localhost providers. The prior Stage 4 trial
spent two subscribed Codex sends: one unknown with 8,000 units reserved in
its separate scratch space, and one answered with 868 reported tokens.

## manual-acceptance

The exact PowerShell setup and launch commands are in
`docs/core-v0.1/STAGE4-IMPLEMENTATION.md`. They create a new synthetic space,
working directory, input Artifact, Activity and proposed Work inside ignored
`_scratch`, then start ordinary Pi. Review `/zara-status` before and after a
fresh Pi session. Check the linked Artifact, rights, current reserve and
proposed status. Only the owner may invoke `/zara-accept` for the reviewed
result; this correction has not accepted the owner's Work.

## next

solmax

# Core v0.1 Stage 4 interactive Pi implementation

## outcome

The owner accepted preparatory commit `adc725866bd8c3a7f1fc73e6f5c836febc0652a1`
and authorized the interactive Stage 4 path on `codex/core-v0.1` in
`C:\my_global_workflow\core-v0-1\zaratustra`. Ordinary upstream Pi 0.87.0 now
connects to independent Core through the installed Zaratustra extension and
loopback bridge. A selected Work receives exact current inputs, a persistent
Attempt and pre-send model reserve. A completed answer becomes an Artifact and
separately linked Work output. Work remains `proposed` until explicit acceptance.
No standalone RPC executor, production DBOS or dispatcher was added.

## evidence

The source specification still has SHA-256
`1DDCBF9DBFD58426781F61A67A170D3CE85FCD2BA27B17549773ED3356F9428D`.
`docs/core-v0.1/STAGE4-IMPLEMENTATION.md` describes the implemented boundary.
Focused tests cover current execution/model rights, stale inputs before send,
unknown reserve after a fresh session, explicit acceptance, and deletion.
The synthetic localhost Pi run used `/zara-work` to choose Activity/Work, matched
the SHA-256 of the final provider HTTP body to Core's pre-send invocation,
saved an answered result and left Work `proposed`. A separate `/zara-accept`
input and confirmation changed it to `succeeded` with a recorded basis. A
budget-refused run persisted `prepared` and sent zero provider HTTP requests.
The wheel includes `pi_adapter/extension.ts`.

The first subscribed Pi request used provider `openai-codex`, model
`gpt-5.6-luna`, SSE transport and low reasoning. Pi reported an invalidated
authentication token after send; Core kept that invocation `unknown` with its
8,000-unit reserve. The owner completed Pi's standard ChatGPT Plus/Pro (Codex)
login. A second subscribed request through the same provider/model/transport
answered the synthetic text with 868 reported tokens. Core saved `The note is
fictional.` as an exact Artifact and Work link. A fresh local authority read
the same `proposed` result, current Work rights and 868 committed / zero held
units from SQLite.
Only fictional scratch workspaces and the subscribed Codex path were used.

The final full `uv run --locked python -m tools.check --deliver` passed:
178 formatted files, clean Ruff, strict mypy on 152 files, 21 import contracts,
484 tests, source/wheel build and report structure. The final check includes
the current-rights snapshot and Pi's no-tools default.

## assumptions

The actor is established from an explicitly confirmed local console and OS
account, then bound to space id and execution epoch. The Codex Provider is forced
to SSE because Pi's default WebSocket path is not observable through the
available final-request `fetch` hook. A positive Pi auth readiness check can
still precede a server-side token rejection. Token units are the provider's
reported usage; a response above its reserve is still charged and prevents
further admission at an exhausted limit.

## cuts

Automatic publication covers one text output slot. Multi-slot and non-text
outputs need an explicit future output path. Unknown model outcomes retain
reserve and are not auto-refunded. This stage does not implement a standalone
RPC executor, DBOS connection, automatic resumption, provider-side data
retention, or Core-managed deletion of Pi's external session JSONL. It does not
read real user documents or modify `C:\projects\zaratustra`.

## cost

Two actual subscribed model HTTP sends out of the owner's ten-call trial cap:
one rejected after send with unknown usage and 8,000 units held in its separate
scratch Core space; one answered with 868 reported tokens and zero held in its
own scratch Core space. No service or retry calls were sent in the real trial.
Local synthetic provider runs are outside the actual model-call count. No paid
API key or paid API endpoint was used. Model/provider/budget paths and rights
remain configurable product inputs; trial values are not hard coded.

## manual-acceptance

In a fresh space authorized for the local console actor, choose a Work through
`/zara-work`, run one synthetic or otherwise authorized text summary, then
reopen Pi and inspect `/zara-status`. Check the saved exact Artifact, output
link, current rights, reserve and `proposed` Work. Use `/zara-accept` only after
reviewing the text, enter a basis and confirm the displayed Work revision and
output. Confirm `succeeded`, its receipt and an `ongoing` Activity. The
subscribed trial Work remains `proposed`; engineering evidence does not accept
that result or the Stage 4 implementation on the owner's behalf.

## next

solmax

# Historical Core v0.1 Stage 4 plan and scenario 9 check

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
