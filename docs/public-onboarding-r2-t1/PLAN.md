# Public onboarding R2 T1 — Process material and terminal Result

call: c-solmax-zaratustra-public-onboarding-r2-t1-20260914
mode: PROBA; engineering_contract: 36
public_basis: fbca9f9e36242dbcf3410241c9178d51fb66c3d1
branch: codex/public-onboarding-r2-t1
worktree: C:/my_global_workflow/7974/zaratustra

## Bounded effect

This T1 adds two Core meanings and no onboarding coordinator. First, an exact
immutable byte value can be saved as a Process-owned material without naming or
creating a Work. Second, `submit_result` can finish its exact source Work without
creating a continuation. Both effects use `apply_mutation`, the existing exact
local authorization binding, one global revision, one event and one receipt.

The implementation does not add a Process lifecycle/status, hidden Work, sentinel
continuation, latest-Work selection, planner, alternate journal, agent adapter,
installer/updater or private path. Released migrations 1–7 and old request/event/
receipt bodies remain unchanged.

## Decisions W28–W32 and A05–A09

| Row | T1 decision | Disposition |
|---|---|---|
| W28 / A05 | Add a first-class immutable `ProcessMaterial` value to the canonical Mutation event. Its exact bytes live in schema-8 `process_materials` inside the same SQLite transaction and are verified against the event-retained digest/size on history and content reads. The Process record carries the new global revision. The request targets an exact Process and revision; trusted local authorization is bound to the complete request. No Work or Work authority is borrowed. | Implement in T1. |
| W29 / A06 | Keep released request 4 as Result+next. Request 6 admits a Result only when `next_work` is absent. Migration 8 rebuilds `work_results` with nullable `next_work_id`, copies every released row and body unchanged, and stores terminal Results in the same canonical table. Event/history/result readers treat continuation as optional while retaining exact source Artifact, closure, completion identity, revision, fingerprint and receipt. | Implement in T1. |
| W30 / A07 | Current Work is the unique Work in the selected Process whose status is `draft` or `ready`. Zero is a normal `None`; more than one is invalid history. `RecordsSnapshot.current_work` and the Process-material listing report this fact without a read-side write or historical fallback. Caller/catalog Work ids remain inputs that other readers revalidate, never authority. | Implement the canonical Core predicate and no-current read in T1. Common readiness/entry prose remains T2. |
| W31 / A08 | T1 does not add a general later-Work creation operation. Released atomic Result+next remains readable and usable. A later ordinary Work requires a new explicit request, fresh authorization/revision/idempotency and Pack compatibility; it must not reopen a completed Work. | Decision recorded; public later-Work admission remains T2. |
| W32 / A08 | A valid Pack snapshot with no following occurrence returns `None` from the rule and produces request 6 terminal submission. It does not say the Process is complete. Malformed, noncanonical, wrong-binding and changed-history snapshots still refuse. | Implement the terminal distinction in T1; later explicit Work construction remains T2. |
| A09 | Add explicit schema 8. Keep migrations 1–7 byte-stable. Migration 8 changes only the current Result table shape by copy and adds material content storage. One history replay validates released continuation events and new terminal/material events together after restart. No sidecar reader or old-event rewrite exists. | Implement in T1; real two-release updater/fence/recovery remains T5. |

## Authority, identity and failure order

Old Work mutations retain their established order. A Process-material save validates
input, exact Process authorization, current revision, retained history and operation
identity, then exact bytes before inserting the material, advancing the Process/global
revision, event and receipt in one transaction. A refreshed exact duplicate returns
the original receipt; a changed intent collides. Missing/wrong authorization, stale
revision, wrong Process, changed bytes or identity collision writes nothing.

Terminal Result keeps the released source Work checks: current Work rights, exact
global/source revision, duplicate/collision discipline, exact Result reference and
complete verified basis precede the atomic done/event/receipt/result row. A committed
terminal Work remains done and cannot be reopened or completed twice; `read_result`
is the recovery path for a lost reply.

## Evidence plan

Focused behavior tests cover migration of a released Result+next workspace with old
row/event/receipt bodies unchanged; old/new mixed history after restart; terminal
Result with truthful no-current; post-terminal material save/read/restart; denied,
wrong, stale, changed-content, duplicate and collision cases; and Pack exhaustion
without `process_complete`. Existing Result+next, context, binding and construction
tests must remain green. Delivery evidence is the full
`uv run --locked python -m tools.check --deliver` report.

## Cuts and remaining tasks

T2 still owns common readiness/resume prose, entry/catalog reconciliation and the
explicit ordinary later-Work admission. T3–T7 retain onboarding composition, agent
assets, install/update/recovery, fictional release gate and owner/private passage.
This T1 is not a public release, updater proof, personal acceptance or Direction G5.

END_OF_FILE: docs/public-onboarding-r2-t1/PLAN.md
