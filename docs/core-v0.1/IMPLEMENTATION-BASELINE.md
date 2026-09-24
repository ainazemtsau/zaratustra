# Core v0.1 implementation baseline

## Authority

This baseline records the owner's September 22, 2026 instruction to implement
the approved engineering plan for the new Zaratustra Core v0.1. The source
specification is:

- Canonical repository copy: [Zaratustra_Core_Specification_v0.1.md](Zaratustra_Core_Specification_v0.1.md).
  All stages read this copy; preserve its exact bytes.
- Original import path: `C:\Users\Anton\Downloads\Zaratustra_Core_Specification_v0.1.md`
- SHA-256: `1DDCBF9DBFD58426781F61A67A170D3CE85FCD2BA27B17549773ED3356F9428D`

The new product starts with empty domain state. Existing `.zara` workspaces and
legacy product data are not migration inputs and must remain unchanged.

## Repository baseline

- exact base commit: `9913786eacb9c95ce103e29a21fa1e89dbdbd070`
- implementation branch: `codex/core-v0.1`
- Stage 2 starting commit: `7ec6033d234b0e2e870f53796a9dad0711d3b468`
- earlier CALLs, Works 1–8, M0/M1 plans and acceptance records: retained history

## Completed Stage 1 boundary

Stage 1 was limited to:

1. G08-1: test the published upstream Pi `0.87.0` Provider, RPC and UI extension
   surfaces with localhost-only synthetic traffic and no real model account.
2. G07-1: test DBOS `3.0.0` durable execution with a fixed SQLite runtime and a
   synthetic domain fixture whose database remains separate from DBOS state.
3. Record each gate as `positive`, `negative`, or `inconclusive`, including exact
   versions, hashes, commands, observations and anything not tested.
4. Run the repository's complete PROBA delivery check.
5. Stop before the Core v0.1 domain schema or Pi/DBOS production dependencies.

The gate environment may install exact dependencies only in disposable,
isolated locations. It must not repair or alter the user's global npm, access
secrets, contact paid model services, modify user data, or write old `.zara`
workspaces. A published-artifact run may be followed by at most one targeted
rerun for an inconclusive setup or source-build discrepancy.

## Continuation authority — September 22, 2026

After the initial Stage 1 result was recorded in local commit `705c336`, the owner
authorized one new full run of each corrected stand and up to two targeted repeats
after a diagnosed error. This continuation did not authorize production dependencies,
Stage 2 implementation, a Pi fork, a custom dispatcher, real provider credentials or
non-localhost traffic. The initial attempt limit above remains a historical statement
about the earlier completed work; it was not used to limit or relabel the continuation.

## Authorized Stage 2 boundary — September 22, 2026

The owner separately authorized the independent domain-foundation stage from exact
commit `7ec6033d234b0e2e870f53796a9dad0711d3b468`. The technical plan is
`docs/core-v0.1/STAGE2-PLAN.md`. This stage may implement:

1. a new empty space with its own identity, schema and authoritative SQLite database;
2. typed addressable Artifact, Decision and Grant records, immutable revisions,
   managed text/bytes and provenance;
3. one atomic mutation path with exact operation identity, current revisions,
   audit and receipts, including exact replay and lost-response recovery;
4. trusted-local current authorization with distinct execute/read-result rights;
5. model-free inspection plus the backup/restore, deletion, connection-closing and
   bounded-busy maintenance required by data introduced in this stage;
6. synthetic direct tests, a reproducible model-free example and full PROBA delivery.

The new foundation does not import or change old spaces. Pi and DBOS remain outside
production dependencies. Scheduler/dispatcher, Attempts, Work execution, Activity
creation, memory, Sleep and developer workflows remain outside this stage and are not
stubbed. DBOS-dependent execution stays blocked; return to DBOS only after stable
Windows evidence for closed handles and removal of managed technical payload, without
silently narrowing the deletion guarantee or automatically choosing a custom runner.

## Preserved engineering rules

Python/uv, Pydantic, package boundaries, PROBA, `tools.check`, STOP/STEER,
nearest-file `AGENTS.md`, mirrored tests, fictional fixtures, separate temporary
workspaces, local-only checks, and the exclusions for CI/CD and push automation
remain in force. `validation.config` and `REVIEW.md` are unchanged unless a
repeated concrete conflict is separately approved.

END_OF_FILE
