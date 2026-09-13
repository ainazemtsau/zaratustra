# Public onboarding T1 technical handback

## outcome

T1 selected one minimal recovery boundary for later implementation: immutable
program/connection release slots plus a fenced, complete same-path recovery root,
with migrations first exercised on an isolated copy. DB-only recovery is falsified
by current load-bearing state outside SQLite. The implementation/evidence commit is
`dd2e16883576b6e7d46876dbdb0bf058d66164fe`; its exact parent/public starting point
is `25be04cdd28dbd5894a99095f61a014a9e566483` (product 0.15.1).

This result is a risk probe and committed PLAN, not a shipped updater, onboarding
coordinator, public release, owner acceptance, or independent-user proof. T2 was not
started.

## evidence

- `docs/public-onboarding-t1/PLAN.md` maps W18–W25 and A03 to current files/seams,
  inventories all found mutable carriers outside SQLite, records three exact reuse
  matches, compares three different topologies, and records the remaining sequential
  task boundaries without changing W01–W17/K01–K11.
- `tools.probe_public_onboarding_t1` built and installed the current wheel in an
  isolated environment and used public product APIs. The passing retained run is
  `_scratch/public-onboarding-t1-02`; its wheel SHA-256 is
  `34b8a3889ceb741fbc5f7576558751c7b85a1f678aad41731b3c61a2b76bb7f5` and its
  installed connection is `zara=zaratustra.cli:main`.
- The migration copy moved schema 2 to 7 while the source stayed at 2. Workspace
  identity, revision 1, the exact record graph, current Work id, and `draft` status
  remained unchanged.
- The recovery scenario reached Core revision 7 with an entry catalog, first-use
  plan, two immutable artifact versions, intake journal/lock, creation journal/lock,
  saved external request, projection, and exact publication/acceptance receipts.
  Removing `inbox/first-use/plan.json` returned `progress_unavailable`, falsifying
  DB-only recovery. Restoring the complete quiescent pair recovered the exact file
  manifest, workspace identity, catalog target, revision, receipts, and
  `selected_work_ready` continuation without another effect.
- Focused native check passed formatting, lint, strict types, 17/17 import contracts,
  the runtime behavior test, and build. The full
  `uv run --locked python -m tools.check` passed formatting/lint/types, 17/17 import
  contracts, 372 tests in 141.15 seconds, and wheel/sdist build.
- The required bounded read-only evaluator confirmed branch/base/origin/config facts
  but its sandbox could not execute the worktree venv. The executor resolved that
  setup-only limitation with an authorized locked invocation: product 0.15.1 imported
  from this checkout. `uv sync --locked` also passed after authorized access to the
  managed uv cache.
- Final `uv run --locked python -m tools.check --deliver`: PASS, including report
  structure, the same native surfaces, 372 tests, and both build artifacts.

W18 remains T4 public pin/install/README evidence. W19 remains T2 read-only
readiness/resume. W20 remains T4 thin Codex/Claude assets. W21 remains T3
prose/capability/draft composition. W22 remains T2/T3 shared stage/receipt
reconciliation. W23 remains T2 initialized-empty admission. W24 is now bounded for
T5 by the selected topology but has no installed updater yet. W25 remains T6's full
fictional release matrix. A03 is answered for PLAN by the surviving topology,
conditional on T5 proving a real two-release transition and cross-process write fence.

## assumptions

The snapshot was taken only after public API operations returned and no product
operation was open. That quiescent single-process boundary is sufficient to test the
full-root topology, but it is not the required future cross-process exclusion.
Current catalog-relative paths were restored to the same selected path. A future
updater must include or explicitly refuse any unfinished-stage external file outside
the declared recovery root.

The current wheel/CLI identity is enough for this early risk probe. It does not stand
in for the absent Codex/Claude connection assets or prove compatibility with another
release.

## cuts

No installed updater, combined coordinator/readiness, initialized-empty activation,
prose intake, Codex/Claude asset, README install rewrite, release/version bump, second
product version, concurrent-writer protocol, private/personal workspace, real data,
provider call, automatic research, GitHub transport, Pi/router work, independent user,
30-day migration, CI/CD, notification, paid service, Direction OS mutation, or T2.

## cost

One committed development-only installed-wheel probe, one runtime behavior test, one
product decision page, and a three-line tools boundary note. No runtime dependency,
schema, Core/Mutation behavior, product package surface, external service, or expense.
One installed probe retry corrected an overly broad provenance assertion; the second
run passed. The full native gate passed on its first run.

## manual-acceptance

pending. All authorizations and data in the probe are fictional local technical
fixtures. No owner or independent person has accepted or used this update boundary,
and no public release has been produced.

## next

solmax

END_OF_FILE: RESULT.md
