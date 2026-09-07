# Product RESULT — Zaratustra Work 1

call: c-solmax-zaratustra-m0-bootstrap-20260907-work1
engineering_contract: 36
mode: PROBA
repo: C:/projects/zaratustra
direction: solmax
node: g-zara-m0-continuity
task: t-zara-m0-foundation

## outcome

WORK1_IMPLEMENTED_AND_LOCALLY_VERIFIED / REPORT HOME.
Version 0.1.0 installs separately from its workspace. Installed `zara init` creates
the planned workspace layout and SQLite bootstrap state through explicit migration
v1; later installed invocations read the same identity/time/schema and DB bytes.
Implementation and measured checks are ready for owner/Direction acceptance.
No owner-performed runtime test or fresh Direction G5 has occurred in this session.
This is Product evidence, not a Direction close. Work 2–8, T1 and M0 remain open.

## evidence

product_basis: 512c7a1657aee9295a1e2e826eb3abc698d05fd8
implementation_commit: bbeae5c17d53e7f24dca22bbd9403cd39c19d094
branch: codex/work1-workspace-foundation
Implementation diff: 16 files, 599 insertions, 44 deletions.
Exact diff: `git diff 512c7a1657aee9295a1e2e826eb3abc698d05fd8 bbeae5c17d53e7f24dca22bbd9403cd39c19d094`.
Raw commit/stat: docs/work1/evidence/implementation.txt.
Raw source/test/packaging/probe diff: docs/work1/evidence/implementation.patch.
The subsequent report commit contains this RESULT and evidence only; it does not
change the measured product source, package metadata, instructions or tests.

wheel: dist/zaratustra-0.1.0-py3-none-any.whl
wheel_sha256: 4f71d1b2aff54d8680d22e01cb58483681a69969c3c3501667e2bb5aabb9482c
Observed runtime: Python 3.13.7, SQLite 3.50.4, Pydantic 2.13.5, uv 0.8.22, Windows.

| CALL done_when | Observed result and exact artifacts |
|---|---|
| 1. Minimal installable core/cli/tests/docs; pinned installed zara outside checkout; repeatable instructions. | PASS in executor's local run. pyproject.toml installs `zara = zaratustra.cli:main`; public Core/CLI and mirrored tests are in the implementation commit. README.md and docs/work1/INSTALL.md document build, locked dependency export, isolated installation and first/repeated run. Raw install-probe.txt shows site-packages outside checkout, no editable/PYTHONPATH dependency, `zara 0.1.0`, compatible locked dependencies and installed executable invocations. |
| 2. Empty-folder init, SQLite, explicit migration v1, persistence on subsequent installed run without manual repairs. | PASS in executor's local run. core/migrations.py creates workspace and schema_migrations transactionally with application/schema markers; core/workspace.py implements init/read. The probe creates an empty temporary folder and runs installed `init`, `status`, `init`, `status <path>` in separate OS processes. Each reports workspace_id `fd41ac02-08a3-4cd1-9b98-fd3fcd2a0966`, created_at `2026-09-07T14:04:01.946862Z`, schema 1. Complete DB SHA-256 before/after: `ffd3980c198493b1c49b46b2f8b70f34070dcf87d6bda5ea72b0f0bf9940ffef`. No DB/Markdown repair contributed to this trial. |
| 3. Product RESULT with commits/diff/raw checks, assumptions/cuts/cost/manual acceptance/HOME, W19–W27 preserved; no later completion claims. | This full report plus docs/work1/FOUNDATION.md contains every named disposition. Native `--deliver` checks report structure and cited-artifact presence; it does not decide acceptance. Works 2–8/T1/M0, external proof and fresh close verification are expressly unclosed. |

Commands and raw outputs from the committed implementation:

| Command | Result | Raw evidence |
|---|---|---|
| `uv sync --locked` | exit 0 | docs/work1/evidence/sync.txt |
| `uv run --locked python -m tools.check` | exit 0; formatting/lint/types, 2 boundaries kept, 20 tests, wheel/sdist build | docs/work1/evidence/check.txt |
| `uv run --locked python -m tools.probe_install` | exit 0; non-editable wheel, separate installation/workspace, migration v1 and restart preservation | docs/work1/evidence/install-probe.txt |
| `uv run --locked python -m tools.check --deliver` | final report gate, native checks and build; raw run retained alongside this report | docs/work1/evidence/deliver.txt |

Tests exercise hidden persistence, migration history/integrity, no rewrite on repeat,
nonempty/missing-folder refusal, unknown-schema/corrupt/partial-state refusal and
transactional rollback after an injected migration write failure. Invalid DB fixtures
exist only in disposable tests, never as repaired acceptance data. The 20 tests include
13 existing development-gate checks and 7 bootstrap cases.
One initial development check rejected duplicated scaffold module docstrings/import
placement; corrected before the implementation commit. The next full check passed.
No independent review findings or refuted dispositions are claimed.
review: n/a — PROBA v36; no frozen pair or mandatory product review artifact.
close_evidence: executor's in-session runtime checks only; binding fresh-session G5 not performed.

## assumptions

- The exact Work 1 mechanics conform to plan §§4.1,6.1,26–29,41 under existing
  owner-ack:solmax-plan-conforming-20260907; comparison is in FOUNDATION.md.
  This applies existing delegation and does not invent an owner runtime verdict.
- Direct local init into an explicitly selected empty folder bootstraps metadata
  before Work exists. It accepts no Handoff/approved/actor grant and creates no
  permission for later mutations. OS filesystem access is the present boundary.
- SQLite metadata is the source of truth. UUID and UTC time are bootstrap facts;
  schema_version is not a domain revision. No owner identity or personal data inferred.
- Read-only repeat init/status support only schema v1. Filesystem creation and DB
  commit are not one atomic filesystem operation; interruption may leave a refused
  partial folder. No automatic cleanup/repair, process-kill recovery, power-loss or
  hostile same-user race guarantee is asserted. See FOUNDATION.md for scope.

W19–W27 disposition, with full answerer/decision timing/rewrites in FOUNDATION.md:

| ID | Disposition |
|---|---|
| W19 | Open, PLAN before dependent domain/replay work; duplicate-first not selected. |
| W20 | Open, PLAN for artifact publication/commit/recovery/rebuild; only bootstrap DB transaction resolved. |
| W21 | Bootstrap-only answer recorded above; trusted caller/current authority/receipt-read/scope remain open before first Work and dependent mutations. |
| W22 | Open, PLAN for snapshot/dependent revisions/scoped references/budget/manifest. |
| W23 | Open, PLAN for actual clean-chat delivery/response protocol and evidence; no chat simulation is acceptance. |
| W24 | Work 1 formats/schema/CLI/transaction/BUSY/identity/time/layout/failure retention resolved; future operation/revision/recovery mechanics open. |
| W25 | Open, PLAN for fictional Process fixtures and foreign-context negative case. |
| W26 | Local package, installed command and workspace layout verified; permanent personal folder, external install/upgrade and hosting decisions open. |
| W27 | Only init/read seams needed now; E1–E12 later detail remains open, no incoming M1+ prerequisite or invented API. |

## cuts

Only Work 1. Work 2–8, Process/Work/Artifact/Event/revisions, Mutation/Handoff/context,
M1+, MCP, real Process, full migration and external independent-install proof are
outside this admission. No required Work 1 done_when was silently cut.
CI/CD, GitHub Actions, notifications, their setup and test pushes remain excluded
by owner-ack:solmax-zaratustra-work1-no-automation-20260907 and the product receipt
docs/setup/OWNER-DECISION-20260907.md. No remote publication/account, costs or new
external rights were exercised. No Direction OS or old repository was written;
no archives were read. No personal workspace was selected.

## cost

One single-agent implementation leg; approximately 20 minutes elapsed (estimate,
not a precise billing measure), within the half-focus-day calibration. No new
service/API spending. Exact token/subscription cost is unavailable. Existing managed
uv/Python and cached dependencies were reused. The sandbox required normal local
uv/cache and Git write escalation; both were approved. No tool remained unavailable.

## manual-acceptance

Owner runtime acceptance: pending; no personal trial has been represented as passed.
Use docs/work1/INSTALL.md: the same installed commands and locked installation steps
as tools/probe_install.py, with a disposable folder retained for a second terminal.
Expected: `zara 0.1.0`, then stable workspace_id/created_at/schema_version=1 across
init/status/re-init and another terminal invocation. Full DB byte equality is checked
by the automated probe. Its temporary installation and workspace have been removed
by the probe; the built wheel and committed raw outputs remain in the product repo.
This trial is not the Work 8 M0 demonstration or an independent participant's proof.

## next

next: solmax
HOME: return this complete Product RESULT and its evidence for Work 1 acceptance
and the required fresh close-evidence check. Only Direction may consume its CALL
or admit Work 2. The executor neither edits Direction state nor issues its successor.
T1 keeps its existing binding fresh-session G5/light eligibility rule; this Product
RESULT does not discharge that rule or mark T1/M0 done.

END_OF_FILE: RESULT.md
