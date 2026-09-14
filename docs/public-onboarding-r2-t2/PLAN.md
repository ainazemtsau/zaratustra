# Public onboarding R2 T2 — truthful Process resume and later ordinary Work

call: c-solmax-zaratustra-public-onboarding-r2-t2-20260914
mode: PROBA; engineering_contract: 36
public_basis: ecb559423d3639c42bb74df7ca8a0cb16d0f1441
branch: codex/public-onboarding-r2-t2
worktree: C:/my_global_workflow/64ee/zaratustra

## Bounded effect

This T2 completes W30/W31 and A07/A08 with one Core invariant. The authoritative
Process read derives the unique draft/ready Work, reports normal no-current state,
and refuses an invalid many-current history explicitly. A separate explicit
Process-scoped request may then create one ordinary ready Work and its declared
Artifact. It uses the existing Mutation transaction, local authorization, global
revision, immutable event, operation fingerprint and durable receipt.

There is no read-side write, historical fallback, initial-record shortcut, reopened
terminal Work, hidden/sentinel Work, automatic next Work or Process lifecycle state.

## Decisions W30 / A07

- `read_process_state` remains the common Core read. Its returned value derives a
  `current_work`/`no_current_work` resume status from the same canonical snapshot;
  zero unfinished Works is normal and one is returned exactly.
- More than one draft/ready Work is corrupt authoritative history. Reads return an
  explicit `ambiguous_current_work` failure instead of selecting by order. The
  failure discloses no guessed current identity and performs no repair or write.
- The read remains Process-scoped with exact workspace/Process/revision and trusted
  local authorization. Entry prose and agent rendering remain T3/T4.

## Decisions W31 / A08

- Add explicit schema 9 for the new semantic event; migrations 1–8 and every old
  record/event/receipt byte remain unchanged. Schema 9 adds no table: it admits one
  new canonical `work_creation` event in the existing journal.
- `WorkCreationRequest` names the Process, new Work/Artifact identities, the complete
  ordinary Work value and the exact saved `PackReference`. Core admits it only when
  the Process has no current Work, the binding matches exactly, identities are new,
  authorization/revision are fresh and the operation id is new or an exact replay.
- The transaction advances the Process and global revision, creates one ready Work
  with `work_metadata` scope and matching Pack binding, creates one declared Artifact,
  and commits one event/receipt. It cannot alter or reopen an old Work.
- The trusted `process_packs` host resolves the exact installed registration both
  when building and immediately before applying the request. Missing/incompatible
  packs refuse before Core mutation; Core independently refuses unbound or changed
  saved binding. A Pack supplies no authority and no automatic plan.

## Failure order and recovery

Input/schema, exact authorization and Process lookup precede the fresh global revision
and duplicate recovery; a new intent then requires normal no-current state. A refreshed
exact request may recover the original receipt after a lost response, while changed
intent collides. Stale,
wrong, denied, current-present, reused identities, unbound/mismatched/missing/
incompatible Pack and injected SQLite failure leave state/history unchanged.

## Evidence and cuts

Focused tests cover current/zero/ambiguous reads with byte/mtime stability; terminal
Result -> Process material -> later Work -> accepted Result after restart; refreshed
replay/collision; wrong/stale/denied/current-present/identity conflicts; missing and
incompatible registrations; changed binding; and transaction rollback. The full gate
is `uv run --locked python -m tools.check --deliver`.

T3 retains unified prose/onboarding and entry rendering; T4–T7 retain agent assets,
install/update/fence, release and owner/private use. This task adds no CLI, Pack rule,
planner, installer, updater, release, private path or Direction acceptance claim.

END_OF_FILE: docs/public-onboarding-r2-t2/PLAN.md
