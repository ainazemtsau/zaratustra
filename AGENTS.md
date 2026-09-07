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
This is the setup-only scaffold for M0. The `zara` command, workspace init,
SQLite state/migration v1 and all Works 1–8 remain unimplemented.
`src/zaratustra/core` and `src/zaratustra/cli` are empty module boundaries.
Installed product code and user-chosen data workspace are separate.
Read the current CALL before doing product work; setup admits no successor.

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
