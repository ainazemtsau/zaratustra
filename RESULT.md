# Public onboarding R2 T2 operation-identity correction handback

## outcome

R2T2-G5-01 is corrected by implementation commit
`48147fab7ae595329575c52b3fe779f5d42741f5`, whose exact parent is the prior T2
report commit `5bdda984e0b4c5734c236334b752cd613daed10c`. The prior T2 implementation remains
`de0efbb51475fe2f82348d9b93bb82e3512b9876`, based on public main
`ecb559423d3639c42bb74df7ca8a0cb16d0f1441`.

The existing Core Mutation authority now checks the shared durable operation-id
namespace in both directions. An ordinary Work mutation that reuses an identity
already committed by Process material or ordinary Work creation returns typed
`collision` before any effect. Process mutators continue to reject Work-owned
identities, and exact refreshed replays continue to return the original receipt.

The corrective report is the commit containing this file, with exact parent
`48147fab7ae595329575c52b3fe779f5d42741f5`; its exact commit identity is returned
in the executor handback after that commit exists.

## evidence

- Changed implementation paths are only `src/zaratustra/core/mutations.py` and
  `tests/zaratustra/process_packs/test_work_creation.py`. This report changes only
  root `RESULT.md`; schema, migrations, released history formats, CLI, Pack host,
  projections and artifact code are unchanged.
- R2T2-G5-01 disposition: PASS in corrective product evidence. Reusing the exact
  Work-creation receipt operation id for a valid following `authorize_artifact`
  request now raises `MutationError(code="collision")`, rather than exposing the
  SQLite UNIQUE constraint as `WorkspaceError`.
- Parameterized regression evidence covers both Process receipt kinds
  (`process_material` and `work_creation`) as owners of an id presented to a Work
  mutation. It also covers both reverse Process request kinds presented with a
  Work-owned id. Every collision compares the entire durable `.zara`, artifact and
  projection file set byte-for-byte before and after refusal.
- The same scenarios refresh only `expected_revision` and recover the original
  Process or Work receipt exactly, with the durable file set still byte-identical.
  Changed cross-kind intent never becomes replay.
- Focused pytest
  `uv run --locked python -m pytest -q tests/zaratustra/process_packs/test_work_creation.py`
  passed `9 passed in 8.24s`.
- File-scoped delivery feedback for the two implementation paths passed: both files
  formatted, Ruff clean, strict mypy clean, 17/17 import contracts, the same 9 tests
  passed in 10.25s, and both 0.17.0 distributions built.
- Expanded Core/T2 regression passed `61 passed in 11.61s` across mutation,
  terminal-material, Pack-binding, Result and Work-creation tests.
- Full `uv run --locked python -m tools.check --deliver` at exact implementation
  commit `48147fab7ae595329575c52b3fe779f5d42741f5` passed: 127 formatted files, Ruff
  clean, strict mypy clean over 111 files, 17/17 contracts, `386 passed in 141.17s`,
  both 0.17.0 distributions, and report structure.
- The same full delivery gate on the corrective report tree passed: 127 formatted
  files, Ruff clean, strict mypy clean over 111 files, 17/17 contracts,
  `386 passed in 160.32s`, both 0.17.0 distributions, and report structure.
- A bounded read-only setup evaluator confirmed contract-36 PROBA, the exact
  candidate ancestry, applicable module instructions, no applicable STOP/STEER and
  no product workspace data in the checkout. This is setup smoke only, not binding
  fresh Direction G5.
- Execution receipt: parent Codex task
  `01a09f18-b6a0-7ad2-92c4-176015521998`; executor task
  `01a09f39-8025-7d72-b9dc-9035505929e6`; worktree
  `C:/my_global_workflow/415e/zaratustra`; branch
  `codex/public-onboarding-r2-t2-correction`.

Done_when 1: PASS in product evidence. Work-owned and both Process-owned receipt
identities collide symmetrically before persistence, and exact refreshed replays
remain stable.

Done_when 2: PASS in product evidence. Both Process receipt kinds, changed intent,
rollback/no-effect bytes and reverse-kind behavior are covered while the full suite
retains all existing schema/history and T2 positive/negative evidence.

Done_when 3: focused, implementation-commit and report-tree full gates PASS as above.
The exact report-commit full gate and clean status are returned in the final executor
handback; separate fresh binding G5 remains pending and is intentionally not claimed.

## assumptions

The existing validation order remains authoritative: exact local authorization,
current Work and global revision precede duplicate recovery. The corrective case is
a valid following Work mutation, so the new cross-kind identity check is reached at
the existing duplicate stage without broadening authority or changing refusal order.

The one `mutation_receipts.operation_id` primary-key namespace remains the durable
global identity authority. No second store, inferred lifecycle state or Pack-owned
mutation authority is introduced.

## cuts

No schema or migration change, released-byte rewrite, new request/event/receipt
format, prose/CLI/assets, lifecycle/planner/store, installer/updater/release, private
access, remote action, new right, owner decision, Direction mutation or T3-T7 work.
No integration, push, release or Direction close is claimed.

## cost

Two implementation/test paths and this root report changed. The semantic correction
is three source lines plus focused fictional regression evidence; it adds no runtime
dependency or service. The file-scoped gate needed two bounded feedback corrections
(Ruff formatting, then a mypy loop-variable type conflict) and passed on the third
attempt. The first sandboxed uv invocation could not access the existing user cache;
the same local command then ran with approved access. No destructive reset/clean,
push, release, paid service or external workspace access occurred.

## manual-acceptance

pending. Automated evidence and bounded setup smoke do not constitute owner
acceptance, integration, release or binding fresh Direction G5.

## next

solmax

END_OF_FILE: RESULT.md
