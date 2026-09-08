# Work 3 — Mutation protocol: PLAN

call: c-solmax-zaratustra-m0-mutation-20260908-work3
mode: PROBA; engineering_contract: 36
product_basis: fe064773dccb2d1f818f1004962043df2ef1edd9
direction_basis: 5f6c8fac9910eff5a6a1b64f45f7e7e5c1570d09
status: W21 boundary accepted by owner; bounded implementation authorized

## Final Work 3 decision after owner response

The owner resolved W21 in docs/work3/OWNER-DECISION-20260908.md. The historical
question below is retained as reasoning history; it is no longer a blocker.
Sizing remains one focused half-day for this DB-only slice with no new dependencies.
Version 0.3.0, explicit schema 3; released v1/v2 migrations remain unchanged.

The exact allowlist is authorize_work (draft -> ready, work_metadata scope),
revoke_work (remove scope, including historical receipt-read),
set_work_requirements (replace executor requirements only within ready Work's
work_metadata scope), and cancel_work (terminal cancellation, no Result/next).
Every operation needs exact local confirmation or already-authorized trusted local
chat caller context. Administrative authorize/revoke require that separate owner
channel; bootstrap/migration cannot grant. Cancelled Work cannot be authorized or
executed again. Revoking its remaining receipt-read scope is still permitted.
Goal, acceptance, boundaries, budget, Process membership and artifact content cannot
be changed by these operations. This mechanically bounds current Work authority.

Receipt-read requires exact confirmed query plus current work_metadata scope;
terminal status alone allows history, revocation denies it. Full records/history
read remains an owner-local filesystem read, never a Work-context endpoint.
There are no secrets or account identities; the trusted adapter is part of the local
application trust boundary. In-process Python code is not treated as a hostile user.

All mutations change the sole initial Work: its revision and global state revision
advance together. Immutable journal entries retain exact request, confirmation,
before/after Work, actor/channel/basis, product version, event id and receipt.
Original initial Event remains unchanged. Journal validation reconstructs the Work
from the first before-image through every change to the current saved Work.
Operation fingerprint excludes expected_revision (stored separately), operation_id
(the lookup key), and confirmation (a delivery occurrence); it includes the complete
intent/work/workspace/provenance/reference fields. Exact authorization digest includes
the entire request, including id/revision, and the resolved workspace path.

Unsupported nonempty artifact references are refused at §5 stage 5. Affected file
projections are an explicit empty tuple: no projection implementation is claimed.
The trusted local-chat seam accepts only an in-process caller context provided by
trusted application code, never a JSON/CLI assertion. No Handoff transport/import,
context compiler, content publication, submit_result or successor Work is introduced.

## Source comparison

The complete registered CALL, product AGENTS.md, validation.config, previous
RESULT.md, Work 2 RECORDS/INSTALL/evidence, Work 1 FOUNDATION and setup owner
decision were read. Direction was read only: Work 2 acceptance, retained-trials,
NOW, CHARTER, mutation/foundation/bet cards, the complete accepted architecture
plan, converge verification input, architecture evidence and both named knowledge
receipts. Source locators and measured hashes are in evidence/sources.json.
The plan hash is 4f90d19fc742ab616301b6b4121880f76c75faaeb1f606c8190a84853d8b3e0e.

The existing delegation permits technical decisions that conform to the plan;
it does not choose a previously unestablished boundary of owner authority.
Architecture candidates are design evidence, not approved implementations.

## Bounded proposed increment and sizing

One Core mutation implementation, explicit schema migration 3, CLI delegation,
persisted events/receipts, hidden-state failure checks and a separate installed
trial on new copies. No dependencies are added. Estimate after resolving W21:
one focused half-day for this bounded DB increment; confidence is conditional on
the chosen trust adapter remaining a small local mechanism. A different trusted
channel requires a new size assessment before dependent implementation.

The smallest useful DB-only operation proposed is an explicitly authorized change
of the existing Work's execution state/limited internal scope, together with a
bounded metadata update under that current scope. The exact operation allowlist is finalized above after W21. No arbitrary patch, content body, file reference,
Result, successor Work, Handoff importer or context operation is admitted here.
Initial creation remains create-once, draft and without grants. Migration cannot
activate a Work or issue permissions.

## W19 — literal order and replay

Technical decision: retain schema -> current Work/authority -> expected revision
-> duplicate -> referenced artifacts -> DB mutation + event -> receipt -> affected
projections. All DB checks and writes share one transaction. A repeated original
request normally has an old expected_revision after its first commit and returns
conflict with no second effect; a now-ineligible Work or revoked authority refuses
before that. Never reopen a terminal Work for replay.

Use a global state revision for optimistic concurrency. Every accepted domain
change, including rights/status changes, increments it. Replaying at a refreshed
revision with the same operation id can reach duplicate checking. The operation
fingerprint binds workspace, Work, operation, payload, references and provenance;
expected_revision is separately stored as the attempted precondition. At duplicate
stage, changed intent under the same id returns collision. At the earlier stale
stage, even changed intent returns conflict: no duplicate lookup precedes §5.

A persisted outcome must be discoverable after a lost reply without a new write or
reopening Work. Proposed narrow receipt-read validates current caller/scope before
lookup; terminal state alone need not forbid historical reading, revoked read
authority does. Exact permission rules depend on W21. Receipt is evidence of a
committed change, never a grant. Result/next-Work unit remains PLAN before Work 7.

## W20 — transaction and failure boundary

Technical decision: preserve explicit SQLite transactions, BEGIN IMMEDIATE,
synchronous FULL and bounded BUSY refusal. Store mutation state, event, operation
identity and receipt atomically before returning. Faults during write/event/receipt
or before commit roll back all DB effects. A lost reply after commit leaves one
durable result; a repeat must not duplicate it. Do not automatically issue a fresh
operation id when the outcome is unknown.

Work 3 accepts no artifact-content references and affects no implemented file
projections. The artifact validation stage must reject nonempty unsupported
references rather than invent hashes or skip validation. Record this empty
projection dependency set honestly. Work 4 must add publication and affected
projection rebuilding to the same protocol before admitting dependent operations.
File atomicity, orphan recovery, rebuild and late availability remain open.

## W21 — accepted local trust and current authority

The owner selected the proposed local console boundary in
OWNER-DECISION-20260908.md. No accounts/login, cryptographic human identity or
hostile same-OS-user process isolation are required. The earlier blocker report is
historical, preserved at 6c9da9e/085e402; it no longer stops this Work.

local.confirm_on_console displays an escaped exact request and current Work,
requires stdin/stderr terminal handles and exact approval, then calls the trusted
Core authorize_local seam. No flag, file or model output issues authorization.
The resulting in-process LocalAuthorization binds canonical request (including
operation id and expected revision) and resolved workspace path. Core checks that
binding, current Work/rights, then revision inside the write transaction.

Trusted local-chat application code may call authorize_local after actual owner
permission and invoke apply_mutation directly, without another console identity
check. This is a trusted adapter seam, not a shipped Handoff/chat importer or a
way for JSON to assert trust. Source_ref and actor describe channel provenance;
these strings alone cannot grant anything. Python application code is within the
accepted local trust boundary, not isolated as a hostile caller.

Initial Work remains draft/none after bootstrap and migration. authorize_work and
revoke_work are narrow administrative mutations backed by exact owner-channel
confirmation; they are not Work self-grants or another updater. Execution metadata
requires current ready/work_metadata; terminal Work never restarts. Revocation
also removes scoped receipt-read. Owner-local records/history inspection retains
its existing filesystem boundary and is not presented as a scoped Work-context API.

Every successful mutation stores its actual confirmation with exact request and
before/after images. A stored mutation receipt never grants future authority.
Automated testing simulates owner-channel input on authorized fictional copies;
it is executor evidence, never a human-identity assertion or owner runtime PASS.

## W22–W27 carried forward

| ID | Current decision/disposition | Remaining answerer, point and rewrites |
|---|---|---|
| W22 | Proposed single DB snapshot and global revision includes rights/status and every admitted state change. No stale target-only revision shortcut. | PLAN before Work 4/6: artifact availability, decision/membership dependencies, scoped context, budget and delivered manifest. rewrites: snapshot/context contracts and checks; freshness/scope/budget remain required. |
| W23 | No clean-chat claim or new chat created. | PLAN protocol before Work 6/8, exact delivered input and real separate response in Work 8; rewrites: delivery/demo. Unprovable clean surface remains a blocker. |
| W24 | Proposed UUID operation identity, canonical JSON/SHA-256 intent, separately saved expected_revision, UTC time, explicit v3 migration; v1/v2 released bytes stay fixed. | PLAN finalizes formats after W21; recovery/cleanup before each dependency. rewrites: local mechanisms/tests/migrations; semantic changes return W19–W22. |
| W25 | Only retained fictional samples and new copies; no second full Process. | PLAN before Work 5/6/8: negative foreign-context/reference fixture; rewrites: fixtures/tests/demo. Link integrity is not context isolation. |
| W26 | Actual clean basis/branch/no-remote and version 0.2.0 confirmed. Retained samples must be hashed before/after any use; only new copies may change. | Permanent folder, hosting, independent external install/upgrade remain future admissions; rewrites: package/layout/docs, reassess with external consumers. |
| W27 | Keep one public Core mutation seam for future callers; no incoming M1+ prerequisite. | E1 Process independence, E2 real use, E3 memory provenance, E6 state/context, E8 shared mutation, E9 permissions, E10 transport, E11 installation stay with future consumers. E4/E5/E7/E12 receive no invented direct M0 API. rewrites: public Core/data and consumer migrations; cheap replacement unproved. |

## Verification plan after W21

Measure first commit, original replay, refreshed duplicate, collision, stale input,
terminal Work, current/revoked rights, forged input authority, wrong Work/Process,
receipt disclosure, unsupported artifact references, interleaving and DB failures.
Inspect persisted state/event/receipt values through product reads and read-only
DB inspection; no source scan substitutes for behavior. Install the exact built
wheel separately, use new workspace copies, retain raw outputs, wheel hashes and
runtime locators. Full native check and deliver remain required for a delivered
implementation; focused results are feedback only.

Work 4–8, M0 closure, owner runtime PASS, Direction CALLs/OS writes, CI/CD, Actions,
notifications, remote publication and external/spend/irreversible actions stay out.
Both no-automation owner acknowledgments from the CALL are preserved.

END_OF_FILE: docs/work3/PLAN.md
