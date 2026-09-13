# Process creation T1 technical handback

## outcome

The bounded T1 constructor/runtime risk is validated at product implementation commit
`fec97a4b3f858f174a495ef42fd26b711d65fff8` from exact basis
`2b21060fc9d52d5f9ed7931482eb4892d04cb30a`. Version 0.13.0 adds one generic
immutable definition/snapshot adapter under the existing public `process_packs`
surface. It retains graph nodes, acyclic dependencies, definition editions, exact
result data, traceable request/research/capability reasons, and explicit recurring
occurrences, then deterministically projects one eligible occurrence onto the existing
focused Core Work.

Definitions with invalid dependency targets/self-edges/cycles, incomplete or
out-of-order results, unknown reason sources, or unsupported capabilities refuse.
The Pack rule also refuses noncanonical bytes, changed definition/binding/Work meaning,
and changed prior accepted history. It grants no authority and writes no alternate
state; the existing Core confirmation and mutation path remains authoritative. Core,
migrations, immutable binding semantics, CLI, existing fixture rule bytes, and user
workspaces are unchanged.

## evidence

- `uv run --locked python -m tools.probe_process_creation --case small --output
  _scratch/process-t1-small-fec97a4` exited 0 at the exact implementation commit. It
  selected recurring `capture` occurrence 2 with occurrence 1's exact `note` ground.
  Accepted snapshot SHA-256:
  `80f0691a06ed4b2467d0708e1c16904696d7adc4d6929a2770611d7f75db9efe`.
- `uv run --locked python -m tools.probe_process_creation --case project --output
  _scratch/process-t1-project-fec97a4` exited 0 at the same commit. `assemble` was
  blocked first by two dependencies and then one; after both predecessors it was
  selected with distinct `request_fact` and `research_fact` data and distinct result
  digests. Accepted snapshot SHA-256:
  `76de1183664931898c526651ed4e2d67c98a47709ca35593ad6a9da14ebe0cac`.
- The scoped native gate exited 0 with 16 construction/probe tests and all 15 import
  boundaries kept. It includes one real public-Core lifecycle: bootstrap, exact Work
  requirements, immutable Pack binding, Artifact publication, Handoff acceptance,
  Pack proposal, confirmed Result submission, and inherited continuation binding.
- The retained `docs/process-t1/STEER.md` history-continuity finding was valid. Each
  Work now pins the exact prior canonical snapshot digest. Two sibling regressions that
  replace earlier predecessor data refuse with `history_mismatch`.
- `uv run --locked python -m tools.check` exited 0: 108 files were formatted, Ruff
  passed, strict mypy passed over 94 source files, all 15 import contracts were kept,
  all 330 tests passed in 117.21 seconds, and the 0.13.0 wheel/sdist built.
- `uv run --locked python -m tools.check --deliver` separately exited 0 with the same
  file/type/boundary/test/build counts, 330 tests in 104.41 seconds, and the required
  report-structure gate passed.
- `docs/process-t1/READOUT.md` describes the public APIs, observable traces, refusal
  behavior, repaired defect, exact commands, and limitations. The two definitions and
  all invented values are confined to `tests/fixtures/process_creation`; the installed
  product never imports tests/tools under an executable import-linter contract.

## assumptions

A future activation flow will create initial Core records from `initial_records`, set
the matching `initial_requirements`, and bind the separately selected exact
`PackReference` through existing trusted Core operations. Each accepted domain result
is represented as the canonical full `ProcessSnapshot`; later tooling must preserve
those bytes. Declared node order is the explicit deterministic serialization policy
when several domain nodes are eligible.

## cuts

T1 adds no interactive constructor, draft-question/discovery lifecycle (W10), manual
research request/return lifecycle (W11), activation/first-use CLI (W14), full
recovery/status (W15/W17), or safe definition-edition change policy (full W13/A02).
It adds no universal/parallel scheduler, database, arbitrary code/expression
interpreter, loader, automatic provider/browser/account call, paid service, external
integration, workflow/CI, terminal Core operation, real domain data, or installed
example. Completion of the finite fixture is observable but not mapped to new Core
semantics. The separately requested fresh verifier remains a post-handback action.

## cost

One installed generic module and public exports, one new import boundary, two explicit
development-only JSON fixtures, focused behavior/integrity and real-Core tests, one
development probe with two cases, a minor version bump, and bounded plan/readout/report
documentation. No new runtime dependency, migration, external right, or expense.

## manual-acceptance

pending. These are technical executor observations only; they do not constitute owner
acceptance, Direction close, or the fresh separate verification required after
handback.

## next

solmax

END_OF_FILE: RESULT.md
