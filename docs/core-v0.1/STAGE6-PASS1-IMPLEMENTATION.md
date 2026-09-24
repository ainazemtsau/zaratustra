# Core v0.1 Stage 6, pass 1 — model-independent composition

## Authority and boundary

The owner authorized only pass 1 of [STAGE6-PLAN.md](STAGE6-PLAN.md) on 2026-09-24,
starting from `3ca96c8719a68acb6250d56731b457f0e12c4f6a` on
`codex/core-v0.1`. The permanent repository copy of
`Zaratustra_Core_Specification_v0.1.md` has SHA-256
`1DDCBF9DBFD58426781F61A67A170D3CE85FCD2BA27B17549773ED3356F9428D`.
The implementation uses fictional local content and does not invoke a model.

## Persistent contract

`upgrade_composition_space` explicitly upgrades only active schema 4 to schema 5.
Opening or reading an old schema does not upgrade it. Schema 5 stores immutable
`method_versions`, exact `work_plan_revisions`, child ownership and issue
addresses, exact `work_obligation_revisions`, and Method deletion jobs. Every
mutation uses `apply_operation`, the existing transaction, audit and receipt.
The backup manifest admits schema 5 and contains these tables in the same
checked Core SQLite snapshot.

`CreateMethodVersionRequest` writes one exact `MethodDefinition` and returns a
SHA-256 checksum. Its typed contract contains instruction, applicability,
named inputs and outputs, obligations, role Method versions, required
capabilities with source, and definition source. The first pass accepts only
`always` applicability at the wire level and explicitly refuses an application
requiring unconnected capabilities or role Methods. `MethodRef` pins id,
version and checksum in `WorkState.method`; `method="none"` remains valid.
`method.write` authorizes version creation/deletion; current `method.use`
Decision/Grant authorization is rechecked for dependent actions in the
Activity scope. A new version does not change a pinned Work.

`CreateCompositeWorkRequest` atomically creates the parent, currently known
children, plan revision 1 and **every** declared obligation instance.
Obligations are created even when their intended child role is not yet planned.
They start `active/open`, keep stable Method keys and cannot be made satisfied
by omitting or deleting a child. `ReviseWorkPlanRequest` uses an exact
expected plan revision. Before any child is issued or parent output linked it
can change the rationale, basis and structural conditions or add children;
existing child identity/state and named Method inputs remain pinned. Old plan
revisions remain readable. This pass does not replace or remove a child from
the plan after creation.

`IssueChildWorkRequest` is a subject-level issue operation, not a Pi/DBOS
Attempt. It checks the current plan, Method use, current Artifact basis,
applicable read/execute rights, and exact readiness. An accepted predecessor
output is inserted as an exact input of the issued child. A different operation
id cannot issue that child again; replay of the same request returns the
original receipt. The supported structural conditions are fixed `all`/`any`
members and exact accepted output, succeeded Work, current Artifact or active
Decision revision. Unsupported kinds fail validation; content is never
interpreted as a predicate.

`ConfirmObligationRequest` requires the exact accepted child output and
current Artifact revision, stores an explicit basis and moves only the named
instance to `satisfied`. The existing `AcceptWorkRequest` remains a separate
operation for parent and child. For a parent, the shared Core gate checks full
materialization, all active obligations, each current evidence Artifact,
the plan completion condition, and the exact binding of parent output slots to
accepted child output slots. It also checks current rights and pinned Method.
The parent reaches `succeeded` only after this operation; its Activity remains
`ongoing`. Child linking and acceptance require current issuance and
dependencies. Stale or deleted Artifact content, stale plan revision, revoked
rights, and missing child results stop the dependent action.

The same `apply_operation` gate rejects Stage 4/5 execution, publication,
assignment, continuation and invocation operations for composite parent and
child Works with `unsupported_composite_execution`. The assigned-control read
also refuses them. No Attempt or outbox is created on a subject refusal.
Legacy `method="none"` operations keep their prior route.

## Exact reads and maintenance

`read_method_version`, `read_work_plan` and `read_obligation` require current
read authority and return the requested exact version/revision, without
falling forward to latest. They remain available after process restart.
Quarantine restore preserves schema 5 history, rotates the execution epoch,
and requires fresh recovery before ordinary reads. Deleting a child preserves
the parent's obligation. Parent deletion first requires its children to be
deleted, then removes its plan and obligation payload and redacts replayable
receipts. An active Work blocks deletion of its pinned Method version.
Deleting a now unused Method version removes its definition payload, marks
affected backups contaminated, and creates a pending sanitation job.
`complete_deletions` purges contaminated packages, checkpoints and sanitizes
the live store, and finalizes exact captured jobs.

The package initializer admits the configured exact SQLite DLL before importing
submodules that load `sqlite3`. This applies to an ordinary fresh process and an
installed wheel, without development `sitecustomize` or manual preload.

Partial deletion also sanitizes dependent content in schema 5. Deleting a child
Work retires every plan revision that embeds its state. Deleting an Artifact
retires plan revisions with its structured reference. A confirmation whose
evidence or plan dependency was deleted loses its copied basis and evidence;
the declared obligation remains and its current status becomes `open` in a new
revision. The dependency check follows fixed readiness roles, including
descendants; an independent confirmed role keeps its exact evidence and history.
A sanitized historical revision returns `content_unavailable` at its
exact address; it is never returned with substituted prose. A sanitized current
plan likewise refuses dependent actions and parent acceptance. The parent Work
and its Method requirements remain, but this first pass has no repair operation
for a plan whose current revision was sanitized. Retired operations lose their
replayable receipts/fingerprints, and affected managed backups are contaminated.
`complete_deletions` then purges old packages and sanitizes the closed live
SQLite file; a newly created backup contains only sanitized state.

Sequential deletion needs durable dependency addresses after a plan becomes
unreadable. The sanitized plan payload therefore retains a validated index of
role identifiers, fixed readiness edges and exact Artifact UUID references
from the plan and current Work states. It contains no Work goals, plan rationale,
confirmation basis or Artifact bytes. Public plan reads still return
`content_unavailable`. A later child or Artifact deletion follows this index
through dependent roles, retires their confirmation history and receipts, and
reopens only affected obligations. Independent confirmations remain exact.
The index survives process restart and managed backup. The schema 5 definition
is unchanged. An older sanitized plan without the index cannot recover its lost
edges; later deletion conservatively retires its confirmed obligations rather
than claiming missing dependencies are absent.

## Reproduction and limits

`tests/zaratustra/foundation/test_composition.py` exercises A → B, two
obligations, one pre-execution plan revision, separate child and parent
acceptance, restart in a second process, early B, missing child, cycle,
stale plan/Artifact, revoked Grant, replay/conflict, transaction rollback,
Method deletion refusal, backup, quarantine restore and sanitation.
The correction regressions also exercise a fresh `-S` process with the configured
DLL, partial child and Artifact deletion through public Core operations,
unaffected exact history, reopened obligations, blocked replay, closed SQLite,
old backup purge, a clean new backup and retention of an independent role's
confirmation. The sequential deletion regression uses three obligations,
two plan revisions, a process restart between deletions, and checks the
dependent and independent confirmations separately. Run
`uv run --locked python -m tools.check --deliver` with the project's verified
`ZARATUSTRA_SQLITE_DLL` set as described in
[STAGE5-IMPLEMENTATION.md](STAGE5-IMPLEMENTATION.md).

This pass has no Pi/DBOS composite Attempt, real provider, mutable external
tool, running-plan revision, Method version transition, waiver,
inactive/unresolved applicability, nested composite Work or migration from
legacy `.zara`. The current parent output binding is an exact accepted child
output; later integration produced by a distinct parent Attempt belongs to a
subsequent pass. A saved structured confirmation records an owner's or
delegate's basis; Core does not prove its semantic truth.

END_OF_FILE
