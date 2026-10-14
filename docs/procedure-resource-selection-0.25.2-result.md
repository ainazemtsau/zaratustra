# Procedure resource selection — 0.25.2

## Scope and cause

The owner reported an ordinary installed procedure refusing its first dispatch.
The installed 0.25.1 product and current source reproduce the same defect with
real local config v2 and fictional public Core operations.

The coordinator read an empty resource snapshot, then selected a registered
project. Selection persisted a resource. The coordinator still inspected the
earlier snapshot and persisted a second fallback resource. Its fresh cardinality
check correctly refused assignment. A later model-created resource worsened the
ambiguity. The first refusal meant an ambiguous selection, not an absence of all
resources. No Attempt, assignment or provider send had started for that procedure.

Existing native/recovery procedure fixtures omitted workspace_config. They
exercised fallback creation and bypassed the configured path. Test totals did not
establish that ordinary installed configuration.

## Correction and boundaries

- The procedure reads the committed resource snapshot after configured project
  selection, before considering fallback creation. Assignment pins the actual
  selected resource ID and revision.
- Project selection verifies current identity/status/root after operation receipts.
  Replaying a creation receipt cannot report a revoked resource as selected.
  Ambiguity and changed roots retain exact diagnostic addresses.
- Legacy setup selects one actual active resource and its actual revision rather
  than combining an invented ID with the first historical resource's revision.
  A revoked history, ambiguity or a different selected directory refuses before
  native executor creation.

Core schema 18, canonical contracts, domain rights, Work acceptance and legitimate
multiple resources remain. Revoked resources are not automatically reactivated.
Unknown/completed-response recovery remains before new dispatch. No text parsing,
domain templates, retry expansion, special Health branch or new store is added.

The repeated-tool-error guard retains its operation/address/stable-code contract.
Both observed failures describe the same unresolved resource ambiguity. Comparing
free error text or resetting after unrelated successful tools would conceal it.

An already affected instance needs addressed ordinary Resource revisions after
backup and a check of its exact resource origins and absence of Attempt pins. Its
Work, inputs, outputs, invocation accounting and history stay in place. This is
maintenance of known duplicate effects, not a shipped arbitrary-resource picker.
Personal details and receipts stay in private evidence.

## Actual checks

- The fresh configured procedure regression failed before correction for both
  personal and registered project roots; existing preselected-resource cases
  already passed. Two actual resources existed after each failing first call.
- Two legacy setup identity/revision regressions failed before correction with
  `not_found` before native dispatch.
- The revoked-receipt and changed-root regressions failed before correction by
  returning false successful selections. Multiple-resource refusal already
  prevented effects, but lacked exact addresses.
- Thirty scoped recovery/workspace tests passed after correction. Ruff, format
  and mypy for the six affected code/test files passed.
- A new legacy refusal assertion initially compared the whole Space before its
  legitimate model pin. The fixture now pins the chosen model through Core before
  the resource-only baseline; the full unchanged-state assertion remains.

- One full `tools.check --deliver` ran: format, Ruff, mypy for 280 sources and
  32 import boundaries passed; pytest reported **1248 passed, 1 failed** in
  1145.21 seconds. The failure is the abrupt managed-client death/reopen test,
  with `SQLITE_IOERR_TRUNCATE` at `PRAGMA synchronous = FULL`. The full gate did
  **not** pass and did not reach its build step. One addressed retry reproduced
  that failure; the following bounded investigation identified test resource
  ownership, described below.
- The exact failed fictional DB/WAL/SHM bytes were preserved. A separate copy
  opened through the public Core, retained its Artifact and matching receipt,
  passed SQLite integrity, and closed with normal default checkpoint behavior.
  This proves readable committed bytes. Two otherwise equal crash/reopen probes
  then distinguished retained versus released `Popen` process HANDLE ownership:
  retaining it reproduced the error; releasing it before the first new client
  opened the same committed content. No delay, retry or SQLite option changed.
  The test previously kept its owning `Popen` variable after kill/wait. Its child
  lifecycle now has a local helper scope that ends before reopening. All original
  crash, exact Artifact/receipt, identity, epoch and backup assertions remain.
  The exact underlying Windows `SetEndOfFile` error is not established; this
  evidence does not claim a new SQLite engine correction.
- The corrected existing space-test file passed its affected native gate:
  **39 tests** in 5.51 seconds, format/Ruff/mypy, hygiene, 32 import boundaries,
  report structure and wheel/sdist build. This was the final addressed retry;
  the whole suite was not rerun or relabelled PASS. Product Foundation bytes,
  SQLite defaults and schema are unchanged.
- The additional ordinary-to-procedure handoff regression passed. Answered
  invocations and a proposed output without terminal final proof retain an
  active Attempt; an exclusive successor refuses with no effects. Exact owner
  interruption releases it while preserving output, accounting and acceptance.
  Automatic host-exit interruption policy is unchanged.
- The affected `tools.check --files` repeat for the recovery test file passed:
  **23 tests** in 44.10 seconds, type/format/lint, 32 import boundaries, hygiene,
  report structure and wheel/sdist build.
- Two ordinary installed Pi probes passed from a noneditable wheel outside the
  checkout, with actual local config v2: personal root and registered external
  project. Each kept one actual resource with the exact Attempt pin and wrote
  a UTF-8 file through Pi's native tool in the selected root, absent from the
  other root. Raw result repairs, full reviews, question/confusion/reopen,
  compact, ordinary first Work and fictional Development continuation passed.
  Each observed **55 HTTP requests and 55 accounted deliveries**; Work was not
  accepted. Local connection-reset messages occurred during client shutdown;
  declared native barriers and exact send accounting still passed (exit 0).
- Final rebuilt wheel SHA256 equals the installed probe candidate:
  `12c20eb3f5effc31e7c646a693e947356e38ebcd6042e53147f39c3f7201670c`.
  Its 124 production members match source and the isolated installation.
- A private verified backup, separate restore and addressed resource repair
  rehearsal passed. User Activity/Work revisions, outputs, data and invocation
  accounting were unchanged. No private content, paths or receipts are included
  here; no real personal procedure or model was started by the rehearsal.

One bounded read-only evaluator verified final wheel/source/isolated-install
equality, schema 18, absence of development-only package members, preserved rights
and acceptance authority, and both configured native reports. It identified no
resource-fix/package blocker and correctly refused to call the original full
gate PASS. The subsequent addressed harness investigation and check resolve that
observed failure without changing product behavior.

Normal product cleanup closes coordinators before the owned Core client. A
source-only observation remains: workflow's separate daemon exit watcher is not
explicitly joined in `_close_owned`. No reproducer established incorrect effects
or the observed harness failure in that product path; it is not reported fixed.

## Private installation and maintenance

The owner-authorized installed instance was updated from 0.25.1 to 0.25.2 after
verified backup and restore rehearsal. All 124 installed production members
match the final wheel. Post-install readback found its Core state unchanged.

Addressed ordinary Resource revisions revoked the two proven duplicate effects,
keeping their history and the canonical configured resource. The exact prior
ordinary Attempt was interrupted after the owner confirmed window closure; its
answered invocations and proposed result remain. Final readback confirms the
Activity/Work revisions, all original data/result bytes, inputs, acceptance and
accounting remain, including independent Development. Schema 18 and instance
configuration remain. No model, procedure dispatch, Work acceptance, export or
private Git publication was performed by maintenance. Detailed evidence stays in
the private archive.

## Public publication

The verified shared code is published in `ainazemtsau/zaratustra/main` at
`c4516ce99a673e985e34c90041ae0e52c0ec5df0`. Authenticated GitHub commit readback
and fetched Git main agree; fetched production files and 0.25.2 metadata match
the checked source. The publication report adds no wheel bytes. Unrelated local
untracked materials are preserved and not included. Private instance evidence,
answers and operational receipts are not published.

Final private readback again confirms preserved Health/Development history,
results and accounting, one active procedure resource and addressable duplicate
history. No real Pi subscription or paid API requests have been made for this
package. Code checking, publication, private installation and owner acceptance
are separate facts.
