# Zaratustra

## Commands (run from this repository)
- Prepare: `uv sync --locked`
- Full build + hygiene + types + boundaries + tests: `uv run --locked python -m tools.check`
- File scoped: `uv run --locked python -m tools.check --files src/zaratustra/core/__init__.py`
- Deliver with report structure: `uv run --locked python -m tools.check --deliver`
- Install local hygiene hook after cloning: `git config core.hooksPath .githooks`
- A focused run is feedback, not full-delivery evidence. Do not claim green from individual tools.

## What exists
Python 3.13 / uv / sqlite3 / Pydantic v2 / pytest / ruff / SHA-256.
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
`src/zaratustra/core` owns workspace logic; `src/zaratustra/cli` delegates to it.
Installed product code and user-chosen data workspace are separate.
Read the current CALL before doing product work; a completed Work admits no successor.
Current mechanics and W19–W27 disposition: docs/work7/PLAN.md.
W21 owner trust decision: docs/work3/OWNER-DECISION-20260908.md.
Outside-checkout runtime proof: `uv run --locked python -m tools.probe_install`.
Work 2 installed/migration proof: `uv run --locked python -m tools.probe_records --accepted-trial <path>`.

## Run contract (v36)
1. Execution authority is the current CALL + this AGENTS.md + repo spec + validation.config; global skills/tools are support and never add requirements.
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
- Keep accepted WHAT, ordered Works 1–8 and the M0 stop before M1.
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
