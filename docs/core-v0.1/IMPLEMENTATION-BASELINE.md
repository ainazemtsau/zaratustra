# Core v0.1 implementation baseline

## Authority

This baseline records the owner's September 22, 2026 instruction to implement
the approved engineering plan for the new Zaratustra Core v0.1. The source
specification is:

- `C:\Users\Anton\Downloads\Zaratustra_Core_Specification_v0.1.md`
- SHA-256: `1DDCBF9DBFD58426781F61A67A170D3CE85FCD2BA27B17549773ED3356F9428D`

The new product starts with empty domain state. Existing `.zara` workspaces and
legacy product data are not migration inputs and must remain unchanged.

## Repository baseline

- exact base commit: `9913786eacb9c95ce103e29a21fa1e89dbdbd070`
- implementation branch: `codex/core-v0.1`
- earlier CALLs, Works 1–8, M0/M1 plans and acceptance records: retained history

## Authorized implementation boundary

The current implementation is Stage 1 only:

1. G08-1: test the published upstream Pi `0.87.0` Provider, RPC and UI extension
   surfaces with localhost-only synthetic traffic and no real model account.
2. G07-1: test DBOS `3.0.0` durable execution with a fixed SQLite runtime and a
   synthetic domain fixture whose database remains separate from DBOS state.
3. Record each gate as `positive`, `negative`, or `inconclusive`, including exact
   versions, hashes, commands, observations and anything not tested.
4. Run the repository's complete PROBA delivery check.
5. Stop. Do not start the Core v0.1 domain schema or add Pi/DBOS as production
   dependencies without a separate transition to Stage 2.

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

## Preserved engineering rules

Python/uv, Pydantic, package boundaries, PROBA, `tools.check`, STOP/STEER,
nearest-file `AGENTS.md`, mirrored tests, fictional fixtures, separate temporary
workspaces, local-only checks, and the exclusions for CI/CD and push automation
remain in force. `validation.config` and `REVIEW.md` are unchanged unless a
repeated concrete conflict is separately approved.

END_OF_FILE
