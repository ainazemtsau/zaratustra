# Public onboarding R2 T3 correction 2 engineering handback

## outcome

Binding G5 r2 F3 is corrected in implementation
`e7f5d61e567abdd817c0184b766fbad1b1baf3a5`, whose exact parent is failed report
candidate `7359be8fd8f7ea87b3c1f3e3d66dadfe74dd1268`. That report's exact parent is
F1/F2 correction `32c0fedba33b790bcbb594c66ec989f8cd2e2bf0`, whose parent is failed
original T3 report `37ee54153080acae02a0d8edaba4f47f3f5f6191`. Earlier ancestry remains
original T3 implementation `01076ed9470202aef51f84d0561b76fa1b1c4382`, then accepted
R2 T2 `daaafe55653c38eaefe36e468858aa68a21429d0`.

This separate report commit has implementation
`e7f5d61e567abdd817c0184b766fbad1b1baf3a5` as its exact parent. Its own identity and
post-commit full deliver result are supplied by the final handback; a report cannot
truthfully contain its own commit identity.

First execution and exact receipt recovery now derive warnings from public Core
`read_projection_status`, after reconciling the committed Result receipt. An
unresolved missing/stale overview yields `rebuild_required` on both responses.
Unchanged Core/projection state produces identical full stdout. An explicit rebuild
before replay truthfully removes the warning while preserving the full receipt and
all remaining response fields. Status is an observation at the Core read; it does
not guarantee filesystem state after that read.

No transient stderr is persisted; no journal field, schema, Core mutation or second
authority is introduced. Exact original Result confirmation is still required on
replay. Recovery writes nothing and does not resubmit or rebuild. Only the existing
ProjectionRebuildError is reconciled as committed; other submission and projection
read errors propagate. The exact rule and commands are in
`docs/public-onboarding-r2-t3/CORRECTION-2.md`.

Implementation changes exactly these five paths:

- `src/zaratustra/process_change/__init__.py`
- `tests/zaratustra/process_change/test_process_change.py`
- `tools/probe_public_onboarding_r2_t3_correction.py`
- `tests/tools/test_public_onboarding_r2_t3_correction.py`
- `docs/public-onboarding-r2-t3/CORRECTION-2.md`

This report adds only root `RESULT.md`. Core, process_packs, CLI, onboarding,
dependencies, schema, validation.config, AGENTS.md and all T4+ files are unchanged
from candidate 7359be8. This engineering return does not close T3 or establish
integration, release, owner acceptance or binding G5 r3.

## evidence

Authority: current CALL
`c-solmax-zaratustra-public-onboarding-r2-t3-correction-2-20260914`, contract36 PROBA,
original T3 CALL/PLAN, prior correction documentation and binding G5 r2 F3 evidence.
The named Direction CALL/evidence were read only; Direction was not modified.
No root STOP/STEER was present during work.

Executor task `01a0a000-a9e3-7b43-9bff-2d8fd2717829`, cwd
`C:/my_global_workflow/d60b/zaratustra`, HOME task
`01a09f18-b6a0-7ad2-92c4-176015521998`. Exact clean detached HEAD and parent were
verified before creating branch `codex/public-onboarding-r2-t3-correction-2`.
The required bounded read-only setup evaluator independently observed that clean
detached baseline, contract36 PROBA and absent STOP/STEER. It made no product change
and ran no tests; it is not binding G5. The old coordinator was not messaged.

START RECEIPT delivery to HOME was rejected by automatic approval review, which
described it as initiating an unauthorized delegated workflow. No workaround was
used. The requested DLP fallback is the complete final handback in this executor
task; any successful final factual handback and verification will be reported there.

Baseline wheel SHA-256:
`771f709c6b7140d60c0dd759e0d72bb404ad5126d0849c4a4ee1fb656ebe3ffe`.
It was built from unchanged baseline product bytes. The extended installed harness
retains its initial observation under `_scratch/t3-correction-2-before`; wall time
22.0040005 s. Both first apply and fresh retry returned rc0/applied and the same Core
receipt. First warned rebuild_required; retry warnings were empty, although both
projection reads reported stale_or_changed. Exact operation
`1b7bb000-5afb-45b5-9105-a9d3cc162ed7` produced one revision/event; replay bytes stayed
unchanged. Full first/retry stdout SHA-256 respectively:

- `d307a914fd583ff0dc515e39d928a0830f9305221053352a902db27004757e7a`
- `54e3c8859ac58c8f46f5231b136b9baf0cf19a512d2588787b37f6f88062152d`

The new F3 regression failed on the unchanged product specifically at warning
equality: `1 failed, 2 deselected in 16.69s`; wall 18.7165757 s. Log:
`_scratch/t3-correction-2-baseline-regression.log`. A second fresh installed baseline
scenario also failed the full stdout assertion, rc1 in 4.433157 s, retained at
`_scratch/t3-correction-2-baseline-recheck/correction.json`.

At exact implementation e7f5d61, the installed after-probe passed in 19.2669249 s:
`uv run --locked python -m tools.probe_public_onboarding_r2_t3_correction
--output _scratch/t3-correction-2-after`.
Corrected wheel SHA-256:
`800f82d5f4b12f1048c2f2f432ba0a254380da3204b5f765e624e0a843aafe92`.
The retained wheel-only installation verifies all product modules load from it;
fictional setup fixtures are explicitly exposed by the development harness only.

After first/retry PIDs 95940/105852 both returned rc0/applied. Both complete stdout
SHA-256 values are
`750356bd68e0e0a30f3fd237a9580e561a927db79ea9582fe08704f6e60d71d7`.
Both include exactly:
`rebuild_required: Result committed; projections/overview.md is stale_or_changed; rebuild from saved state`.
Both public projection status objects are identical at authoritative revision 10.
Operation `4aea82f3-02a3-492a-98cc-6759f20a9fd0` has one history event; first apply adds
one event/revision and retry changes no selected state file. First process faults
exactly one overview replacement; the retry has no injected fault. First apply
confirms Context and Result; replay confirms only original Result digest
`d9f6426f7bc57f203bb969a4884a5c4d97dc47864d67effead3fa652129820bb`.
Missing/wrong confirmations refuse without byte changes. Public API recovery yields
the original receipt and same warning. Explicit installed projection rebuild changes
only overview bytes; the next fresh retry reports current/empty warnings, identical
receipt and no additional revision/event. Normal F1 replay and all five F2 unfinished
stage reads still pass with identical output and byte-stable state.

Complete first/retry stdout/stderr, PIDs/prompts, status and hash manifests:
`_scratch/t3-correction-2-after/fresh-cli/correction.json` and its
`projection-failure` subdirectory. The complete 4,808-character F3 stdout files are
`projection-failure/apply-first-stdout.txt` and `apply-retry-stdout.txt` there.

Independent reproduction: copied the previous G5 r2 author's `probe.py`,
`cli_driver.py`, `file_faults.py` unchanged into
`_scratch/t3-correction-2-independent`. This scenario imports neither repository
tools nor test fixtures. Its real console adapters are driven with exact displayed
synthetic digests. A separate scratch `verify_f3.py` wrapper records operation-count,
exact replay authority and missing/wrong refusal hashes, then asserts complete F3
stdout equality. This executor rerun of independent code is NOT a fresh binding G5.
Source/copy hashes are retained in each `independent-contract.json`:

- probe.py: `6c3a0d83056270b548c80217720adaa48786171ad564e8e3d2bffccbcbfe06c8`
- cli_driver.py: `013ed90e7fa4a5a59723999f6287b69669429107eaff7470108607487140b774`
- file_faults.py: `880a71dbf53cb0d4c8ff0f44acdf9983c55803392be1edb849fdb6ee35f102fe`

Run with the retained before/after installed Python respectively:
`<installed-python> -I -X utf8
_scratch/t3-correction-2-independent/verify_f3.py <baseline-or-after>`.
Choose a new label for another run. The unchanged scenario uses 15 fresh CLI
processes; the wrapper adds missing/wrong replay processes, for 17 total per run.
Each run retains 28 checks plus wrapper assertions, complete stdout and module paths.
The copied scenario's summary and wrapper's copied counter still say 15; the exact
total is independently visible in the 17 retained trace result files per run.

- Baseline: expected F3 FAIL/rc1, 10.0485608 s. Operation
  `bfd124c6-50b3-426e-8b8b-31352ab25e5c`, one event/revision, identical receipt,
  byte-stable replay, stale_or_changed, warning lost. First/retry stdout hashes:
  `f202b0abd57c0d79d4fe66b69b43de688daedbfe4569a3f48a41530ae876e9ee` /
  `443aa5ab4e09b92e5238acf498305216845e5e459b35ce598afce7f9540f9eed`.
- Corrected: PASS/rc0, 12.6144223 s. Operation
  `864251fe-0135-43a8-ae13-e6119ed1c2d4`, one event/revision, identical receipt,
  byte-stable replay, stale_or_changed and identical nonempty rebuild_required
  warnings. First/retry stdout SHA-256 is
  `683afbaf5031f53df183cbc79892ba0a4bcb32a21dd59ddd5e3e766c853af1e3`.
  PIDs 58888/105724; original Result digest
  `0d3dad469f9e86eaf44d2dac09c4b9cfc3338336f5e55c58b291ca09d50c3ccb`.
  Evidence: `run-after/independent-contract.json`, `run-after/trace` under the
  independent directory. Review-journal replacement failure also preserves Core
  bytes before its successful explicit retry.

Native focused gate on implementation contents passed four formatted/typed files,
Ruff, 18/18 import contracts, `26 passed in 41.13s`, wheel/sdist build; wall
55.1552256 s. The final harness then added only its post-save F3 equality assertion;
that final tool content was exercised by the exact-commit installed after-probe and
the full native deliver. Log: `_scratch/t3-correction-2-native-focused.log`.

Expanded focused suite at exact implementation e7f5d61 passed
`60 passed in 51.67s`, wall 52.189302 s. Command is in CORRECTION-2.md; it covers
onboarding, creation/change, ordinary Work creation, terminal materials and both T3
probes. Log: `_scratch/t3-correction-2-expanded-focused.log`.

Full `uv run --locked python -m tools.check --deliver` at exact implementation
e7f5d61: PASS; 134 formatted files, Ruff, strict mypy over 117 source files, 18/18 import contracts, 408 passed in 178.69s (0:02:58), both 0.17.0 distributions and report structure; wall 183.5499483 s. Log:
`_scratch/t3-correction-2-implementation-deliver.log`; exact timing/HEAD also retained
in its sibling timing JSON. Full report-tree deliver will run after this separate
report commit; its actual outcome and final clean status belong in the final handback.
Report-presence checks are structural evidence, never semantic or owner acceptance.

## assumptions

Core history/receipt and exact Result authorization remain authoritative. Warnings
are current derived projection diagnostics, not immutable properties of a receipt.
No earlier transient exception text or local journal grants new authority.
An explicit repair can therefore truthfully change warnings on a later retry.

All scenarios use new fictional selected scratch workspaces and synthetic trusted
confirmations. No real external research, person/provider/account, actual interactive
human acceptance or fresh binding review was simulated as an accomplished milestone.

## cuts

Scope is only F3 and necessary regression/reproduction/report evidence. No other
behavior or accepted W/K/PLAN obligation is cut or silently settled. No Core,
process_packs, schema, dependency, user JSON workflow, automatic research, hidden
Work, auto-next, historical selection/reopen, second authority, Solmax-specific
product rule, T4+, installation assets, updater, Direction write, integration,
publication, push, release or personal/private data is added.

## cost

One local implementation commit (five paths, one installed product file), plus one
separate RESULT report commit. Seven behavioral regression cases were added. Product
version remains 0.17.0, Python 3.13.7; no new dependency or infrastructure.

Initial sandbox branch creation and uv setup could not access shared Git metadata
and the managed uv cache; authorized escalated local runs succeeded. START message
was rejected as described above. Baseline F3 assertion failures are intentional
counterexamples, not passing gates. Ruff formatting and import ordering were applied
before native checks. The focused native gate and exact implementation full deliver
each passed their first actual gate attempt. No failed gate exhausted its retry budget.
The first report tree also passed full deliver (408 tests in 183.61s, wall
187.1948598 s). Final trace inventory then corrected only the reported independent
CLI-process total from 15 to 17; the same local report commit was amended and full
deliver rerun on that exact final report tree. No product/test bytes changed.

## manual-acceptance

pending. HOME is solmax for a separate fresh binding G5 r3 of the COMPLETE original
public-onboarding R2 T3 claim. Engineering checks do not establish T3 close, owner
acceptance, integration, T4 readiness or release.

## next

solmax

END_OF_FILE: RESULT.md
