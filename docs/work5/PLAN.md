# Work 5 — Handoff PLAN

call: c-solmax-zaratustra-m0-handoff-20260908-work5
mode: PROBA; engineering_contract: 36
accepted_basis: 0b5ad766545d2cb32c4ef1edfc1cf06fb0e6e35f
actual_worktree: C:/projects/zaratustra/_scratch/work5-handoff
branch: codex/work5-handoff
status: technical decisions recorded before dependent implementation

## Authority, conformity and size

Compared CALL, Product AGENTS/validation.config, Work 4 PLAN/installed evidence,
Work 3 exact W21 owner decision, Direction Work 4 binding G5, architecture
sections 3–7,25–29,41 (SHA-256
4f90d19fc742ab616301b6b4121880f76c75faaeb1f606c8190a84853d8b3e0e),
and the carried W19–W27 agenda. Under
owner-ack:solmax-plan-conforming-20260907 this is conforming HOW: one manual
accepted_result import, retaining literal section 5 and current rights. No new
owner words are claimed. Both no-automation acknowledgments remain in force.

One bounded increment: one value schema/table, one mutation operation, file/stdin
delivery, owner-local saved-result read, hidden consistency tests and installed
evidence. Estimate within half a focused working day; no new dependency, spending,
external right, remote, permanent workspace or deadline. Only new explicitly
selected copies of the accepted fictional observatory graph are mutated.

## W19 — identity, effect, replay, stale, collision and receipt

Handoff version 1 has kind, handoff_id, workspace_id, process, related_work,
intent=accepted_result, source_revision, result (exact Artifact/version/hash),
basis references, provenance, owner_instruction, constraints, open_questions and
created_by surface. Text remains data. Long result content already lives in the
Work 4 immutable Artifact; no replacement set_work_requirements operation.

The effect is an immutable accepted_handoffs record plus Work/global revision,
event and receipt in ONE transaction in apply_mutation. Work status/requirements,
Artifact active_version and permissions retain their meaning. This records the
accepted result for later admitted Works; it neither completes Work nor creates
a successor. Owner-local read_handoffs exposes the full value, first delivery
hash/source, confirmation and receipt from a coherent validated DB snapshot.

handoff_id is the global operation_id. Mutation request version 3 carries the
Handoff and delivery metadata. The full canonical request/path binds permission;
the delivery has SHA-256 of the input bytes and file locator or stdin marker.
Fingerprint excludes delivery metadata and transport expected_revision only:
the same logical JSON through file or stdin has the same intent. Handoff's
source_revision stays immutable. Unknown/duplicate JSON keys and extra authority
fields are rejected; no silent coercion to another command.

Literal order: schema -> current Work/authority -> expected global revision ->
duplicate -> source basis and exact artifact references/availability -> DB effect,
event, receipt -> projections. An original replay is stale and conflicts. Explicit
--expected-revision permits re-delivery against a refreshed current revision with
new exact permission: same id/intent returns the old receipt, changed intent
collides. A NEW operation must also have source_revision=current revision: a
transport override cannot make a stale uncommitted decision fresh. No automatic
retry, new id, rebasing of decision meaning, or duplicate-first ordering.

## W21 — actual trusted delivery and current authority

Reuse the accepted exact interactive console confirmation: preview current Work,
resolved workspace path and complete canonical request, type approve plus digest.
For stdin delivery read the bounded JSON stream to EOF, then independently open
the controlling console (CONIN$/CONOUT$ on Windows, /dev/tty on POSIX). JSON and
an appended approve line cannot become permission. No controlling console means
permission_denied. File delivery uses the existing console path. This is the
actual public CLI channel, not a simulated trusted-chat claim.

The existing trusted in-process local-chat seam remains usable after real prior
permission, without another identity check. Fixtures using it are labeled executor
simulation. No account/login or hostile same-user isolation is added or claimed.
Core revalidates the binding and current ready Work with metadata authority under
the write lock. Import writes metadata and reads only that Work's exact Artifact;
it does not need publication rights and grants none. Foreign Process/Work/workspace,
revoked/terminal Work and mismatched request/path/content authorization refuse.

## W20 / W22 / W24 — storage, availability and public format

Explicit migration 5 adds accepted_handoffs keyed by handoff_id and linked to the
existing event. Released migrations 1–4 stay byte-identical. Existing default
migration target remains 4 for compatibility; Work 5 requires zara migrate --to 5.
Read/init never upgrade. Version 1/2 mutation canonical bytes remain unchanged.

JSON is UTF-8 (optional BOM), bounded to 64 KiB; text fields preserve their exact
characters, with bounded lengths. Schema is exportable by handoff schema. Import
supports handoff import WORKSPACE FILE or '-' for stdin. handoff list is an
owner-local inspection surface, not Work 6 context delivery. Accepted records and
events are cross-checked during reads; no extra unlogged mutation path.

Every first import verifies result and basis version/hash and current bytes, even
when the version is no longer active. Duplicate returns only the historical receipt
without revalidating bytes. Saved metadata never promises late byte availability;
artifact read rechecks it. Work 4 file-before-DB, retained orphan, explicit exact
repair and projection rebuild boundaries persist unchanged. Import creates no new
content file. Post-commit projection failure reports the committed receipt/exit 2;
explicit rebuild changes no state. No broader power/disk-loss durability claim.

## W25 — fixtures and checks

Use new copies of the one accepted fictional Process. Check valid file and stdin,
original/refreshed replay, altered content with same id, stale new decision,
foreign ids/ref/hash, absent permission, forged approved/owner text, changed
request/path, revoked and terminal rights, missing/corrupt historical bytes,
SQLite rollback/commit failure, contention, lost reply and failed projection.
Preserve exact input/output and wheel-installed source hashes outside checkout.
Native build/hygiene/types/boundaries/tests and deliver are required. Earlier
accepted DB/wheel/receipt files are hashed before/after, never upgraded in place.

## Carried W19–W27: answerer, decision point, rewrites

| ID | Answer here / remaining answerer and moment | rewrites |
|---|---|---|
| W19 | Product PLAN before Work 5: effect/identity/replay/stale/collision/receipt above. PLAN before Work 7: submit_result/next unit. | importer, receipts, linkage, failures, migrations; cheap reversal unproved |
| W20 | Product PLAN before import: Work 4 boundary and verified references consumed above. PLAN before Work 7: continuation/recovery. | references, recovery, evidence, migrations |
| W21 | Product PLAN before delivery: exact console/current authority binding above. PLAN before Works 6/7: context/Result consumers. | adapters, permissions; decision is not runtime acceptance |
| W22 | Product PLAN before import refs: immutable versions/hash and source/global freshness above. PLAN before Work 6: scope, budget, dependencies, delivered manifest. | snapshot, context, tests; duties retained |
| W23 | PLAN before Works 6/8: exact delivered input and actual separate answer on five facts in Work 8. | delivery/demo; unprovable cleanliness is a blocker |
| W24 | Product PLAN before Work 5: schema 1, request 3, explicit DB 5, JSON/CLI above. | mechanics/tests/migrations; meaning returns to W19–W22 |
| W25 | Product PLAN before Work 5: fictional positive/duplicate/stale/foreign/unauthorized copies above. PLAN before Works 6/8: context fixtures. | fixtures/tests/demo; no second full Process |
| W26 | Product PLAN before Work 5: accepted local ref and isolated checkout above; separate installed trial. PLAN before permanent folder/hosting/external install-upgrade. | package/layout/docs |
| W27 | Product PLAN before new Work 5 consumer: versioned Core Handoff and saved acceptance/receipt APIs. Later PLAN at each admitted consumer; E1–E12 retained, E4/E5/E7/E12 have no invented direct M0 API. | Core/data/consumer migrations; M1+ not prerequisite |

Return full Product RESULT HOME to solmax, with walkthrough and actual evidence
separate from owner runtime words. No Direction write, T4/M0 close, successor CALL,
binding G5 claim or Work 6 start. Exact 0.5.0 needs its own fresh physical G5.

END_OF_FILE: docs/work5/PLAN.md
