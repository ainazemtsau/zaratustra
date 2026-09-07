# Work 1 — workspace foundation decisions

call: c-solmax-zaratustra-m0-bootstrap-20260907-work1
mode: PROBA; engineering_contract: 36
Product basis: 512c7a1657aee9295a1e2e826eb3abc698d05fd8.
Scope: version 0.1.0, installed Core/CLI, init, SQLite and migration v1 only.

## Plan comparison and authority

Compared with the accepted Direction plan
`live/solmax/work/zaratustra-architecture-plan-2026-09-05.md`, SHA-256
4f90d19fc742ab616301b6b4121880f76c75faaeb1f606c8190a84853d8b3e0e,
sections 4.1, 6.1, 26–29 and 41; setup acceptance and the current Work 1 CALL.
Architecture input `converge-g-zara-m0-continuity-arch.md` is design evidence,
not an accepted implementation. This file resolves only the mechanics needed now.

Executor verdict: the exact decisions below conform to the accepted plan.
Authority is the existing owner delegation, owner-ack:solmax-plan-conforming-20260907:
«В принципе все вот эти моменты авто подтверждать, если не идет какое-то
рассогласование плана». Source: Direction knowledge
`zaratustra-plan-conforming-approval-2026-09-07.md`. No new owner words or runtime
PASS are inferred. No unresolved owner-owned fork needed for this bootstrap was found.

## Current mechanics

- One installed package, `zara` entry point, public Core init/read functions.
  argparse owns presentation; Pydantic v2 validates returned metadata.
- Explicit selected existing folder, default cwd, no parent discovery. First init
  requires empty; the plan's .zara/processes/artifacts/projections/inbox layout
  is created. No permanent workspace is chosen by this session.
- One `.zara/state.sqlite3`. Explicit migration `0001_workspace` creates just
  `workspace` and `schema_migrations`. A random UUID identifies the workspace;
  one UTC ISO-8601 timestamp is stored for creation and migration. Neither value
  is a Work revision, operation identity, user identity or permission.
- Bootstrap authorization is the direct local invocation selecting an empty folder,
  as admitted by this CALL and plan §28 step 1. Core owns this bounded creation
  before Work exists. It accepts no payload, actor/approved flag, Handoff, receipt
  or authority scope, and grants nothing to later mutations. OS filesystem access
  remains the local boundary; same-user hostile-process isolation is not claimed.
- `.zara` creation exclusively reserves initialization. Migration DDL, initial
  metadata, migration digest and version markers commit in one `BEGIN IMMEDIATE`
  transaction. SQLite DELETE journal, synchronous FULL, five-second BUSY timeout;
  no automatic retries. Application ID identifies the Zaratustra DB;
  `user_version=1` identifies this schema, separate from later domain revisions.
- Repeat init and status use a read-only URI and one read transaction. They check
  directory layout, application/schema version, singleton metadata and migration
  history. They reject symlinks/junctions in managed entries, incomplete/corrupt or
  unknown-version state. No upgrades or automatic repairs are attempted.
- Filesystem layout and DB commit are not one atomic filesystem transaction.
  A failure or interruption can leave an incomplete directory. It is retained and
  reported/rejected, never deleted to force success. DB migration rollback is tested;
  process-kill recovery, power-loss guarantees and hostile path races are not proven.
  A later admitted recovery design must address those claims before depending on them.

Python's explicit transaction control and URI read-only opening are documented in
[Python 3.13 sqlite3](https://docs.python.org/3.13/library/sqlite3.html).
The application owns the meaning of
[SQLite user_version](https://www.sqlite.org/pragma.html#pragma_user_version).
These sources support mechanics, not product acceptance.

## W19–W27 disposition carried HOME

All future portions stay open with PLAN as answerer; this table supersedes only
the Work 1 portions of the setup-time OPEN-AGENDA. No row vanishes.

| ID | Work 1 disposition / evidence | Still open and decision point |
|---|---|---|
| W19 | Deferred; init repeat is a read, not a Handoff replay policy. No duplicate-first decision or domain revision introduced. | PLAN before dependent Work 2/3/5/7 decisions: replay/revision/terminal/collision/receipt-read and unit of effect including next Work. rewrites: importer, receipts, failure tests, linkage and migrations; ≤1 day unproven. |
| W20 | Only bootstrap DB transaction implemented in core/migrations.py; no artifact bytes or active references. | PLAN before Work 2–4/7 dependencies: artifact publication/commit/recovery/rebuild and Result continuation. rewrites: durable references, recovery/evidence and migrations; cheap stub unproven. |
| W21 | Bootstrap-only resolved as explicit local init above, without Work or grants. Core owns creation; no self-authorizing payload. | PLAN before first Work creation and later mutations/import/context: trusted caller, current authority, receipts, scope and revocation. rewrites: trust boundaries, import/permission checks. Bootstrap is not a future permission bypass. |
| W22 | Only bootstrap identity and schema version exist. No context/revision snapshot contract chosen. | PLAN before dependent Work 2/4/6/7: dependent revisions, scoped references, budget and manifest. rewrites: snapshot/context contracts and checks; freshness/scope/budget remain required. |
| W23 | Deferred; no chat-continuity claim. | PLAN protocol before Works 6/8, actual clean-chat input/response evidence in Work 8. rewrites: delivery protocol and demo; unprovable cleanliness is a blocker. |
| W24 | Current schema, CLI, transaction/BUSY behavior, UUID, UTC timestamp, layout and retain-on-failure behavior selected above; source, tests and probe demonstrate bounded mechanics. | PLAN before each later Work: operation fingerprints, revisions, domain formats, recovery/cleanup and projection cadence. rewrites: local prototype/checks; semantic changes route to W19–W22. |
| W25 | Deferred; no Process created, no real personal data used. Tests use disposable metadata-only fixtures. | PLAN before Handoff/context/demo: minimal fictional fixtures and foreign context negative case without a second full Process. rewrites: fixture data and checks. |
| W26 | Local Work 1 package/install/layout resolved: 0.1.0 wheel, separate environment, installed CLI; INSTALL.md and evidence/install-probe.txt. | Owner's permanent folder, public hosting/rights and independent install/upgrade remain future decisions. rewrites: metadata/docs before publication; reconsider after external dependencies. |
| W27 | Only Core init/read and CLI seams delivered, supporting C08 and the preparatory part of E11; no incoming M1+ prerequisite. | PLAN before each dependent public decision: E1–E12 detail remains open. E1/E2/E3/E6/E8/E9/E10 need later M0 behavior; E4/E5/E7/E12 acquire no invented direct API. E11 external independent install/upgrade is not proved here. rewrites: public Core/data and consumer migrations; ≤1 day unproven. |

## Verification boundary

Native full check plus the installed CLI probe establish measured behavior.
Hidden-state tests cover exact metadata/DB-byte preservation, migration history,
integrity, refusal without modification, and SQL rollback on an injected write
failure. Invalid fixtures are deliberately constructed only in isolated tests.
They are not DB repairs and never contribute data to the passing installed trial.
No owner-visible wording/tuning is frozen by tests.

CI/CD, Actions and notifications remain excluded by the owner receipts. Works 2–8,
T1, M0, independent installation and binding fresh-session G5 remain unclosed.

END_OF_FILE: docs/work1/FOUNDATION.md
