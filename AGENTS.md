# Zaratustra

## Current product authority — Core v0.1
- The current product basis is `docs/core-v0.1/IMPLEMENTATION-BASELINE.md`, the
  owner-approved Core v0.1 implementation plan recorded there,
  `docs/core-v0.1/STAGE4-PLAN.md`, `docs/core-v0.1/STAGE5-PLAN.md`,
  `docs/core-v0.1/STAGE6-PLAN.md`, this AGENTS.md, and `validation.config`.
  Stage 5 is owner-accepted at `245e7288c08eb4d49c84edd89f01e746a45c37a5`.
  The owner accepted Stage 6 pass 1 at
  `29d887d41f1639dc6ddb354a2039603cb1a30d94`; see
  `docs/core-v0.1/STAGE6-PASS1-ACCEPTANCE.md`. The owner accepted Stage 6
  pass 2 at `d33b676c57b8319cb4a4d2527f64d41fe800c154`; see
  `docs/core-v0.1/STAGE6-PASS2-ACCEPTANCE.md`. On 2026-09-24 the owner
  authorized only a detailed pass 3 plan, now
  `docs/core-v0.1/STAGE6-PASS3-PLAN.md`, and said not to start its
  implementation. Pass 3 implementation, pass 4, real model calls and
  development migration are not authorized.
- Earlier CALLs, ordered Works 1–8, M0/M1 plans and their acceptance records are
  retained as engineering history. They do not prohibit or define the new Core.
- Stage 1 stopped after recording the G07-1 DBOS and G08-1 Pi technical outcomes.
  Stage 2 delivered the independent domain foundation and was accepted by the
  owner at commit `62a173c7d9a875e6709bf2e0dbe0d8d7e7fa31df`. The owner
  accepted Stage 3 at `fa4c1773b0b4a8b75a03702be1e524cf8d5ea7a9`. The
  owner accepted the complete Stage 4 at
  `afa367c10ad949b1610810d4f2e6f106c1a7b7cc`, separately from accepting
  one synthetic Work; see `docs/core-v0.1/STAGE4-ACCEPTANCE.md`. The current
  owner accepted Stage 5 pass 1 at
  `03a3887f7d50aa1dccf8c761ce5bc933a57f86c9`; see
  `docs/core-v0.1/STAGE5-PASS1-ACCEPTANCE.md`. The owner accepted pass 2 at
  `b0b923bfb4c4b42e448b2a5a61dcc39dd3937c3e`; see
  `docs/core-v0.1/STAGE5-PASS2-ACCEPTANCE.md`. The owner accepted pass 3 at
  `8a34c09f342059e4cedc1011e81b83a4272fd289`;
  see `docs/core-v0.1/STAGE5-PASS3-ACCEPTANCE.md`. The owner accepted pass 4 and
  the complete Stage 5 at `245e7288c08eb4d49c84edd89f01e746a45c37a5`;
  see `docs/core-v0.1/STAGE5-ACCEPTANCE.md`. This is separate from accepting
  the synthetic Stage 5 Work.

## Commands (run from this repository)
- Prepare: `uv sync --locked`
- Full build + hygiene + types + boundaries + tests: `uv run --locked python -m tools.check`
- File scoped: `uv run --locked python -m tools.check --files src/zaratustra/core/__init__.py`
- Deliver with report structure: `uv run --locked python -m tools.check --deliver`
- Install local hygiene hook after cloning: `git config core.hooksPath .githooks`
- A focused run is feedback, not full-delivery evidence. Do not claim green from individual tools.

## What exists
Python 3.13 / uv / sqlite3 / Pydantic v2 / pytest / ruff / SHA-256.
Core v0.1 Stage 2 adds the independent `zaratustra.foundation` package: a new empty
`.zara-core` space, typed Artifact/Decision/Grant revisions and managed bytes,
one atomic operation/audit/receipt path, current epoch-bound local admission, exact
reads, model-free inspection and bounded backup/restore/deletion. It does not import
legacy `zaratustra.core`; exact surface and reproduction are in
`docs/core-v0.1/STAGE2-IMPLEMENTATION.md` and `tools.probe_foundation`.
Stage 3 adds an explicit additive schema 2 upgrade, typed Activity/Work revisions,
separate write/accept rights, exact Artifact inputs and output slots, and a manual
acceptance operation. See `docs/core-v0.1/STAGE3-IMPLEMENTATION.md` and
`tools.probe_stage3`. A succeeded Work does not complete its Activity.
Stage 4 adds an ordinary interactive Pi path through `zaratustra.pi_adapter`,
schema 3 resource/Attempt/invocation records, observable provider sends, exact
output publication and separate Work acceptance. The owner accepted Stage 4 at
`afa367c10ad949b1610810d4f2e6f106c1a7b7cc`; see
`docs/core-v0.1/STAGE4-ACCEPTANCE.md` and `STAGE4-IMPLEMENTATION.md`. Stage 5
adds explicit schema 4 and Core-owned durable continuation, one assigned ordinary
Pi RPC through DBOS queue/wait, recovery and stop fencing, and shared maintenance
for Core/DBOS/Pi. See `docs/core-v0.1/STAGE5-IMPLEMENTATION.md` and
`STAGE5-ACCEPTANCE.md`.
Stage 6 pass 1 adds explicit schema 5 Method versions, composite Work plans,
materialized obligations, child issue and separate parent acceptance; see
`STAGE6-PASS1-IMPLEMENTATION.md`. Pass 2 adds explicit schema 6 child Attempt plan
pins, runs an issued child through the same assigned Pi RPC with Core rechecks
before every effect, and derives proposed/ready/running/waiting/blocked/succeeded
from Core records; see `STAGE6-PASS2-IMPLEMENTATION.md`. Pass 2 is owner-accepted
at `d33b676`. `STAGE6-PASS3-PLAN.md` proposes pass 3 in parts 3.1–3.10; none is
implemented.
Work 1 implements installed `zara init` / `zara status`, SQLite bootstrap
metadata and explicit migration v1. Work 2 adds explicit `zara migrate` to schema 2,
initial draft records and consistent `zara records read`. Work 3 adds schema 3,
one mutation API, exact local confirmation, atomic audit/receipts and current rights.
Work 4 adds explicit schema 4, exact scoped versioned artifact publication/repair,
verified content reads and deterministic owner-local projection rebuild.
Work 5 adds explicit schema 5 and exact accepted-result Handoff import from file/stdin,
with separate trusted console confirmation and durable acceptance/provenance reads.
Work 6 adds read-only open_work with exact trusted query, bounded actual manifest,
scope/reference closure and full final revalidation. Work7 adds explicit schema6,
atomic Result/completion/next Work and exact inherited context; Work8 is unimplemented.
M1 T2 adds explicit schema7 and exact immutable Process/Work pack binding through
Mutation API, external runtime registration/resolution and pinned continuation.
Missing/incompatible packs refuse package execution; no in-place version migration.
Technical plan and lifecycle reproduction: docs/m1-packs/PLAN.md and tools.probe_packs.
M1 T3 adds seven derived read capabilities through process_packs.read_capabilities,
exact metadata ProcessQuery scope, one locked revision and separately authorized
selected ContextQuery. Public API and reproduction: docs/m1-capabilities/PLAN.md,
tools.probe_capabilities. T4 adds one finite fictional_lot Process using those exact
contracts; reproduce via tools.probe_first_process and docs/m1-first-process/PLAN.md.
Core and generic process_packs bytes are unchanged. T5 adds development-only
fictional_signal (observe/compare rounds), a shared host and two-process/install
scenarios; see docs/m1-second-process/PLAN.md. T5 passed its full native gate and
binding fresh review (f4e3a26, then fa4e079: 235 tests, 11 contracts); the owner
accepted that step as owner-ack:solmax-m1-second-process-accepted-20260910.
T6 adds process_packs.read_overview: one derived shared view of several explicitly
selected Processes through that same seven-answer contract, with overview_lines and
tools.probe_overview; see docs/m1-overview/PLAN.md. Rows stay independent and the
view writes nothing. T6's owner acceptance and five review rounds are recorded in
RESULT.md at baseline d7304c9. M1 was accepted in the Direction review on
September 11, 2026; this does not establish end-user process creation or daily use.
T4 candidate 46718e4 passed fresh G5 (9c9c978); owner
accepted its testing purpose and requires fictional examples only in dev tests.
T1/T4 examples live in tests/fixtures, outside the installed product. Reproduction
tools explicitly load those external fixtures. See docs/m1-test-only/PLAN.md and
OWNER-DECISION.md there; the earlier G5 does not review later packaging changes.
Entry T4 adds one recoverable exact external-material transfer around the existing
publication/acceptance seam, with coordinator journal/lock and authorized Core
receipt recovery; see docs/entry-t4/PLAN.md and tools.probe_entry_t4.
Entry T5 adds the modest installed first-use coordinator and designation-based
context/manual external-chat request/return path; see docs/entry-t5/PLAN.md and
tools.probe_entry_t5. It uses generic unbound Core records and existing mutations.
Public onboarding R2 T1 adds explicit schema8, Process-owned material and terminal
Result without a continuation. R2 T2 adds explicit schema9, truthful common Process
current-or-no-current read with explicit ambiguous-many refusal, and a separately
authorized Pack-compatible ordinary Work creation event; see
docs/public-onboarding-r2-t2/PLAN.md.
Public onboarding R2 T3 adds the installed common `zara entry` prose/resume/change
composition and one recoverable explicit later-Work plan over those existing
authorities; see docs/public-onboarding-r2-t3/PLAN.md and
tools.probe_public_onboarding_r2_t3.
`src/zaratustra/core` owns workspace logic; `src/zaratustra/cli` delegates to it.
Installed product code and user-chosen data workspace are separate.
For legacy implementation context only, the last pre-v0.1 mechanics and W19–W27
disposition are in docs/work7/PLAN.md.
W21 owner trust decision: docs/work3/OWNER-DECISION-20260908.md.
Outside-checkout runtime proof: `uv run --locked python -m tools.probe_install`.
Work 2 installed/migration proof: `uv run --locked python -m tools.probe_records --accepted-trial <path>`.

## Run contract (v36)
1. Execution authority is the current owner request + `docs/core-v0.1/IMPLEMENTATION-BASELINE.md` + the applicable Stage plan + this AGENTS.md + validation.config; global skills/tools are support and never add requirements.
2. PROBA is the default; only the owner's explicit words select OPORA. This repo enables PROBA only; an OPORA CALL STOPs until its applicable gates are installed.
3. PROBA keeps native build/hygiene, tests for answers not visible by eye, owner/tool STOPs; it owes no frozen pair, independent test-author, stage receipts, mutation, property audit or review artifact.
4. Never use self-written source scanning as product behavior evidence. Hygiene/presence checks below make no semantic acceptance claim. Never test tuning magnitudes or an owner-visible answer.
5. An unavailable REQUIRED tool STOPs by name. A real owner-owned choice or plan divergence goes to the owner; no silent scope cuts. Retry at most 3 times per failed gate, then ESCALATE.
6. Completion in PROBA comes from the owner's words, never tasks/ledger checkboxes. Record actual checks separately from owner acceptance; adding tests beside frozen files is legal, editing frozen bytes is not.
7. Engineering REPORT/ESCALATE returns HOME: `RESULT.md` fields outcome/evidence/assumptions/cuts/cost/manual-acceptance/next; `next: solmax`. Only Direction issues Direction CALLs; never edit Direction OS.
8. OPORA requires independent contract-author/build/review sessions and the CALL-pinned gate surface before BUILD; subagent smoke checks here are not binding fresh Direction G5.
9. Read `STOP` / `STEER.md` before mutation and commands. STOP means halt; read and resolve STEER with the owner's intent, without auto-deleting either.
10. Setup verification includes one bounded read-only evaluator smoke agent; otherwise delegate only when the CALL or owner explicitly asks. Inherited model defaults; no provider identity gate.

## Owner scope — 2026-09-07
CI/CD, GitHub Actions and push notifications are excluded requirements until the owner separately asks. Do not configure them or block setup/delivery on their absence, even if a generic checklist requires them. The owner authorized public GitHub hosting and integration into main on September 11–12, 2026; local checks stay required. That authorization does not grant access to user workspaces or authorize paid services. The original automation boundary remains docs/setup/OWNER-DECISION-20260907.md, owner-ack:solmax-zaratustra-local-setup-no-automation-20260907.

## Constitution
- Keep the accepted Core v0.1 functional composition and completed Stage 1–5
  evidence. Stage 5 and Stage 6 passes 1–2 are owner-accepted at the exact
  commits above; this is not owner acceptance of Stage 6. Stage 6 pass 3 has
  planning authority only.
  Preserve earlier Works/CALLs as history, not current scope.
- CLI calls Core through public module surfaces; Core never imports CLI.
- No product writes to Direction OS, old repositories, or unselected user workspaces.
- No real personal data, remote publication, paid service or new external rights without authorization.
- No direct DB/state Markdown edits to fake product success.
- Reuse small native tools before adding infrastructure.

## Conventions
- Managed Python pinned in .python-version; tools pinned in pyproject.toml, dependencies in uv.lock.
- One installable top-level package with nested modules; add new modules to import-linter contracts.
- Cross-module imports use public __init__.py. Add nearest-file AGENTS.md with every module.
- tests/zaratustra mirrors the package; tests/tools mirrors development-only tools/.
- Tests outside tests/, skip/xfail, assertion-free tests, non-portable literals fail hygiene.
- Explorations stay in _scratch/; its content is ignored and tracked scratch content blocks the local commit hook/check.
- The hook runs hygiene only. The full check remains required; its report gate checks presence, never truth.
- Sources use LF. Runtime paths use pathlib; subprocess text capture declares UTF-8.
- REVIEW.md and validation.config changes require explicit owner request or repeated recorded friction.
- Denied actions: force-push, destructive Git reset/clean, deleting unrelated files, reading secrets, edits outside authorized product scope.
- Inherited desktop permissions remain authoritative; repo config does not weaken managed restrictions.

END_OF_FILE: AGENTS.md
