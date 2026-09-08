# Work 2 — initial Core records, version 0.2.0

call: c-solmax-zaratustra-m0-bootstrap-20260907-work2
mode: PROBA; engineering_contract: 36
basis: bc6f053ee62db9a5b711594e73933f1a9cdbf6cf

## Plan comparison and scope decision

The executor compared this increment with the exact accepted Direction plan,
live/solmax/work/zaratustra-architecture-plan-2026-09-05.md, SHA-256
4f90d19fc742ab616301b6b4121880f76c75faaeb1f606c8190a84853d8b3e0e,
especially §§3–7,26–29,41, the Work 1 acceptance receipt, CHARTER, T1/bet,
converge verification-input and architecture evidence, and the two knowledge receipts
named in the CALL. The architecture candidates are evidence, not selected HOW.

Verdict: the bounded mechanics below conform to Work 2 under existing delegation
owner-ack:solmax-plan-conforming-20260907: «В принципе все вот эти моменты авто
подтверждать, если не идет какое-то рассогласование плана». This is the executor's
application of recorded delegation, not a new owner verdict or owner runtime PASS.
No owner-owned choice of real Process, permanent directory or external rights is made.
Sizing: one initial-state slice, comfortably below a focused half-day; not a new deadline.

## Exact mechanics and WHAT equivalence

The names Process, Work, Artifact and Event are retained, as four typed records in
one SQLite core_records table. The table stores id/kind/revision and validated JSON;
core_state stores the snapshot revision. This keeps all operational records in DB,
not in editable state Markdown. Read validates the entire initial graph, including
SQL/body identity, unique ids, Process/Work ownership and Event affected ids.

| Record | Stored meaning now | Boundary |
|---|---|---|
| Process | Generic identity, title, revision, creation time | No Process Pack SDK or domain-specific branch |
| Work | Process, goal, expected result, acceptance, boundaries, budget, draft status; empty context/dependencies/executor requirements | authority_scope=none; not executable, no context compilation or permissions grant |
| Artifact | Identity, title, Process/Work ownership, revision, declared status | active_version=null; no purported bytes, hash, publication or result content |
| Event | Local initial creation, basis, affected ids, Process/Work, time, state revision and actual package version | actor=local-invocation describes the channel, not the human's identity; not a mutation receipt |

An Artifact here declares a future deliverable. Since no file is registered or made
active, §4.2's file→hash→DB→active-reference ordering is not circumvented. There is
no dummy hash, inline long document, or mutable-file shortcut. Work 4 must implement
actual versioned bytes before any active reference or content claim is admitted.

Object revisions start at 1, Event is immutable revision 1, empty state is revision 0,
and initial creation advances the snapshot to 1. Schema version is separate. Only
initial revisions are implemented; no revision increment/update/history-replay API
is claimed. Work 3 must evolve the one Core write entry into the general protocol.
This release refuses additional batches, edits and execution; it cannot serve as
an unguarded updater beside the future Mutation API.

The explicit local records-create invocation constructs initial drafts in an empty
store, before an executable Work exists (§28 steps 2–3, §41 Work 2). Its bounded
authority is to initialize those records in the selected workspace, nothing else.
The CALL authorizes this executor's fictional trial. CLI/Python ability itself does
not prove human approval. No imported owner fields, caller-supplied ids/revisions,
approved flag, Handoff or grants are accepted. This bootstrap gives no future Work
mutation permissions; the trusted receipt adapter and permission enforcement are
still owed before general changes. OS access is the current local read boundary;
this is not scoped Work-context disclosure or hostile same-user isolation.

Both entrypoints call public Core. CLI contains no SQL. Core owns schema checks,
the single initial domain write, and reads. A create transaction revalidates metadata
and emptiness after BEGIN IMMEDIATE, writes four records and revision together,
validates the resulting snapshot, then commits. A repeated create is refused without
a write; this is an initialization guard, not an operation-id/replay protocol.

## Migration and persistence

Released migrations.py/v1 remains byte-for-byte unchanged. New init still creates
schema 1 and its original layout; init/status support both known schemas and never
silently migrate. `zara migrate` explicitly applies 0002_core_records. It preserves
the exact workspace identity, creation time and v1 migration row, adds v2 tables and
its SHA-256 history row in one transaction. Repeat migration on v2 does no DB writes.
The 0.1.0 executable refuses schema 2; there is no downgrade/restore command.

Transactions use SQLite's existing DELETE journal for normally initialized stores,
synchronous FULL, five-second busy timeout, no automatic retry. Queries use mode=ro
and one read transaction; writes use mode=rw so missing DBs are never created by a
records/migrate request. Invalid schema/history/record links are refused, not repaired.
SQLite SQL rollback is measured at migration and Event insertion. Process-kill,
power-loss, hostile path replacement and recovery after filesystem interruption are
not proved. Work 1's incomplete-folder limitation remains.

Mechanics references: [Python sqlite3](https://docs.python.org/3.13/library/sqlite3.html),
[SQLite transactions](https://www.sqlite.org/lang_transaction.html),
[Pydantic models](https://pydantic.dev/docs/validation/latest/concepts/models/).
These describe transaction/model mechanics, not acceptance of the product.

## W19–W27 dispositions

Each row's remaining answerer is PLAN before the named dependent Work. None is
silently closed by a model/table or a passing test.

| ID | Answer needed for Work 2 and implemented disposition | Remaining decision / rewrites |
|---|---|---|
| W19 | Creation-only revisions above; no duplicate-first, terminal reopen, operation id or receipt semantics selected. | PLAN before Work 3,5,7: literal §5 validation order remains the authority; replay/collision/terminal/receipt-read and result-next unit. rewrites: importer, receipts, linkage, tests, migrations; ≤1 day unproved. |
| W20 | Transactional DB creation; Artifact declaration has no content or active reference. Explicit migration rollback and copied baseline preserve bootstrap. | PLAN before Work 4 and related Work 3/7 decisions: publish, hash, commit visibility, orphan/recovery/rebuild and late availability. rewrites: durable references, recovery, evidence, migrations; cheap stub unproved. |
| W21 | Initial Work is a draft with no authority; explicit local bootstrap only, no self-authorizing input. Reads reflect local OS access, not Work-scoped permissions. | PLAN before Work 3/5/6/7: trusted caller/receipt binding, current/revoked authority, scope and historical receipt access. rewrites: adapter, permission checks, import paths; ≤1 day unproved. |
| W22 | Whole initial graph read in one SQLite snapshot; global state revision plus object revisions; no unvalidated external handles. Empty Work context/dependencies explicitly mean not yet compiled. | PLAN before Work 4/6 and dependent Work 3: capture changing decisions/rights/membership dependencies, scoped references, budget enforcement and delivered manifest. rewrites: snapshot/context contract and tests; freshness/scope/budget not cut. |
| W23 | No clean-chat behavior claim in Work 2. | PLAN protocol before Work 6/8; actual separate chat with exact input/response in Work 8. rewrites: delivery protocol/demo; ≤1 day only with available surface, unprovable cleanliness blocks. |
| W24 | v2 explicit migration, typed JSON records, UUIDs/UTC, initial revisions, transaction/BUSY, CLI/create-once/read and retained trial selected and measured. | PLAN for subsequent operation formats/fingerprints and recovery/cleanup. rewrites: bounded local mechanics/tests; semantic changes return W19–W22. |
| W25 | Generic fictional observatory fixture; negative dangling foreign-id fixture verifies stored link integrity only. | PLAN before Work 5/6/8 for foreign-context exclusion/delivered fixture; no second full Process. rewrites: fixtures/tests/demo, previously estimated ≤1 day. |
| W26 | Fresh fact check: accepted product basis/branch, no remote; 0.2.0 separate wheel installation, temporary trial, preserved 0.1.0 original. | Permanent workspace, external independent install/upgrade and hosting remain future admissions. rewrites: package/layout/docs; reassess after outside consumers. |
| W27 | Only initial Core record/read seams C08 and preparatory data for C02/C03/C04; no incoming M1 prerequisites. | PLAN per admitted consumer: E1 Process independence, E2 real use, E3 memory, E6 assistant, E8 frontend, E9 autonomy, E10 transport, E11 independent install. E4/E5/E7/E12 still have no necessary direct M0 API. rewrites: Core contracts/data and consumer migrations; cheap replacement unproved. |

## Verification and retained baseline

Native tools.check covers hygiene, types, the existing two Core/CLI boundary
contracts, hidden-state tests and packaging. New files stay within the existing Core
package, so the existing recursive boundary contracts still cover them.
tools.probe_install repeats the original empty-folder bootstrap scenario using the
new version. tools.probe_records installs the new wheel separately, migrates a COPY
of the retained accepted workspace and creates/rereads records in separate processes.
It also exercises fresh init→migrate→create and leaves a trial for the next terminal.
No DB/state Markdown hand edits establish success. Faults in tests are isolated
negative fixtures. The retained original wheel and DB are hashed before and after.

CI/CD, Actions, notifications and test push stay excluded by both CALL receipts.
No Direction writes, archive reads, old-repository modifications or new external
rights/costs. Work 3–8, T1/M0, owner runtime acceptance and fresh Direction close
verification remain open; the Product RESULT returns HOME only.

END_OF_FILE: docs/work2/RECORDS.md
