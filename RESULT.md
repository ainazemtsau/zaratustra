# Public onboarding R2 T3 correction engineering handback

## outcome

The two binding G5 r1 P2 findings F1/F2 are corrected in implementation commit
`32c0fedba33b790bcbb594c66ec989f8cd2e2bf0`, whose exact parent is failed T3 report
candidate `37ee54153080acae02a0d8edaba4f47f3f5f6191`. That candidate's parent is
original T3 implementation `01076ed9470202aef51f84d0561b76fa1b1c4382`, whose parent
is accepted R2 T2 baseline `daaafe55653c38eaefe36e468858aa68a21429d0`.
The separate report commit containing this file has correction implementation
`32c0fedba33b790bcbb594c66ec989f8cd2e2bf0` as its exact parent. Its identity and its
post-commit full deliver result are returned in the executor handback; a report
cannot truthfully name its own commit.

F1: installed `zara entry change apply` recovers the existing exact committed
request before asking for current Work context. A new effect still needs exact
ContextQuery confirmation; both new execution and receipt recovery still need
separate exact Result confirmation through the unchanged public execution API.
F2: the retained `proposal_pending` action now directs the user to target workspace
selection, the saved proposal's activation preview and exact activation confirmation.
The four other unfinished actions are unchanged.

This is a bounded engineering correction and HOME return for another separate fresh
binding G5 against the complete original T3 claim. It does not close T3 or establish
owner acceptance, integration, release or T4 readiness.

Implementation changed exactly these six paths:

- `src/zaratustra/cli/__init__.py`
- `src/zaratustra/onboarding/__init__.py`
- `tests/zaratustra/process_change/test_process_change.py`
- `tests/tools/test_public_onboarding_r2_t3_correction.py`
- `tools/probe_public_onboarding_r2_t3_correction.py`
- `docs/public-onboarding-r2-t3/CORRECTION.md`

This report additionally changes only root `RESULT.md`. Core, process_packs,
process_change product implementation, schema, dependencies, validation.config,
AGENTS.md and T4+ paths are unchanged from the failed candidate.

## evidence

Execution authority: correction CALL
`c-solmax-zaratustra-public-onboarding-r2-t3-correction-20260914`, repo contract 36
PROBA, original T3 PLAN and the F1/F2 binding review. No applicable STOP/STEER was
present. The executor verified the exact clean detached starting HEAD before
creating `codex/public-onboarding-r2-t3-correction`.

Execution receipt: executor task `01a09fc2-f299-7951-bb4f-f6ccc0252bab`, cwd
`C:/my_global_workflow/c9da/zaratustra`, parent task
`01a09f18-b6a0-7ad2-92c4-176015521998`. START RECEIPT was delivered to that parent.
The old coordinator was not messaged. The required bounded read-only setup evaluator
confirmed the baseline, PROBA contract and absent STOP/STEER; it observed the already
created correction branch, not the earlier detached state. Setup smoke is not G5.

F1 before: the wheel built from unchanged candidate product bytes reproduced first
apply rc0/applied, exact fresh-process retry rc1/change_applied, while the public API
recovered the original receipt. Operation `e6cb5521-4ea6-45cd-a2ce-7de6bdf9e001`
produced exactly one revision/event; retry did not mutate. Complete observations are
retained at `_scratch/t3-correction-before-02/fresh-cli/correction.json`.

F2 before: fresh installed resume showed proposal_pending with a retained proposal,
but Next repeated the research_returned author/retain instruction. Both reads were
byte-stable. The two new regressions failed on exactly F1/F2 at baseline:
`2 failed in 15.92s`.

After: `uv run --locked python -m tools.probe_public_onboarding_r2_t3_correction
--output _scratch/t3-correction-after` completed in 12.5686954 s wall time at the
exact correction implementation. Its wheel SHA-256 is
`771f709c6b7140d60c0dd759e0d72bb404ad5126d0849c4a4ee1fb656ebe3ffe`.
The retained installation verifies all loaded product modules come from that wheel;
only development setup explicitly exposes fictional fixtures. Existing installed
small/project safe-change scenarios and no-change/no-future refusals also passed.

- F1: first apply and fresh-process retry both returned rc0/applied. PIDs were 91468
  and 98780. Complete stdout SHA-256 for both is
  `7b1dfe24d79e5a7d8a452bd308ab4da42479381bd77a1b5a40bf3cf277d1ada5`.
  Operation `3ae5e6be-b38b-4707-abc0-56bcfa163e7e` has exactly one public history
  event. First apply adds one revision/event; replay and missing/wrong confirmation
  refusals preserve every selected change-state file hash. Public API recovery also
  returns the original receipt with identical state bytes. Original receipt output
  can therefore be recovered after a caller loses the first output.
- First apply records two exact confirmation prompts (context, Result); replay
  records only the original Result digest
  `4be73b17ad39679c92751bbfbf623ee76af4ec89c2edfa1592c4dbd3e4e903d6`.
  Missing confirmation uses the real console adapter with closed piped input and
  refuses permission_denied. A valid authorization for a different operation also
  refuses permission_denied. Four additional CLI tests separately deny the initial
  context and Result confirmation with missing/wrong authority and preserve all
  Core workspace bytes.
- F2: the observed Next line is now: Choose the target workspace, review the saved
  proposal's activation preview, and exactly confirm activation. Each of draft,
  research_waiting, research_returned, proposal_pending and activation_pending was
  resumed twice in separate CLI processes. All reads preserve stage-state bytes,
  identical output and zero confirmation prompts; the proposal remains retained.
  The regression distinguishes the two stage actions without freezing their prose.

Fresh-process stdout/stderr, process ids, prompt digests, module paths, stage reads
and state hash manifests are retained under `_scratch/t3-correction-after/fresh-cli`.
The reproducible command and methodology are committed in
`docs/public-onboarding-r2-t3/CORRECTION.md`. These are installed registered-entry-point
checks with synthetic console-seam confirmations, not interactive human acceptance
or a binding independent G5 session.

Native focused gate passed on the implementation contents:
`uv run --locked python -m tools.check --files src/zaratustra/cli/__init__.py
src/zaratustra/onboarding/__init__.py tools/probe_public_onboarding_r2_t3_correction.py
tests/tools/test_public_onboarding_r2_t3_correction.py
tests/zaratustra/process_change/test_process_change.py`.
It passed formatting, Ruff, strict mypy over 5 selected files, 18/18 import contracts,
`19 passed in 18.66s`, and wheel/sdist build; wall time 21.540167 s.

Expanded focused checks at exact implementation `32c0fedba33b790bcbb594c66ec989f8cd2e2bf0`:
`uv run --locked python -m pytest tests/zaratustra/onboarding
tests/zaratustra/process_creation tests/zaratustra/process_change
tests/zaratustra/process_packs/test_work_creation.py
tests/zaratustra/core/test_terminal_materials.py
tests/tools/test_public_onboarding_r2_t3.py
tests/tools/test_public_onboarding_r2_t3_correction.py -q`.
Result: `53 passed in 36.49s`, wall time 37.3034164 s. This includes the original T3
simple/complex prose, manual research, create/resume, Process material, terminal,
explicit later Work, changed/stale/authority refusals and exact replay evidence.
Log: `_scratch/t3-correction-expanded-focused.log`.

Full `uv run --locked python -m tools.check --deliver` at exact implementation
`32c0fedba33b790bcbb594c66ec989f8cd2e2bf0` passed 134 formatted files, Ruff, strict
mypy over 117 source files, 18/18 import contracts, `401 passed in 149.45s`, both
0.17.0 distributions and report structure; wall time 153.240745 s.
Log: `_scratch/t3-correction-implementation-deliver.log`.

The exact report commit full deliver, final clean status and its SHA/parent will be
verified after this report commit and returned to the parent. Report presence checks
are structural evidence only. No product check supplies Direction or owner acceptance.

## assumptions

The existing trusted local adapter and exact public continuation/recovery API remain
the authority boundary. A saved plan or decision is not authority; recovery still
revalidates the current committed request and requires its exact Result confirmation.

Installed probes load the registered wheel console entry point in fresh isolated
Python processes. Synthetic confirmations exercise public authorization for fictional
inputs and are explicitly not owner acceptance. Manual research remains a manual
external transfer; no provider is contacted.

## cuts

Scope is only F1/F2 plus regression, reproduction and reporting evidence. There is
no Core/Pack/schema/dependency change, automatic research, user JSON workflow,
hidden Work, auto-next, historical selection/reopen, second authority, Solmax-specific
product behavior, T4+ assets, updater, release, push, remote publication or Direction
write. Existing W/K/PLAN obligations are preserved and not silently settled.

## cost

One local implementation commit and one separate report commit. Six implementation
paths changed; only two are installed product files. Six regression cases were added,
raising the full test count from 395 to 401. Runtime remains Python 3.13.7 and product
version 0.17.0 with no new dependency or infrastructure.

The existing uv cache/managed runtime and shared Git metadata required approved local
access. Initial sandbox uv sync and branch creation stopped before their authorized
escalated runs succeeded. The first development probe stopped on an incorrect history
field lookup, corrected before its complete baseline run. The native focused gate
used its three allowed attempts: unused test import, typed test patch seam, then PASS.
An intermediate direct pytest run exposed only overly specific error-code punctuation
assertions; these were corrected, and wrong-authority cases now use valid authorization
for a different exact request. The complete implementation deliver passed on its first
attempt. All retries and failures are distinguished from actual green evidence.

## manual-acceptance

pending. Engineering checks and setup smoke do not establish binding G5, owner
acceptance, T3 close, integration or release.

## next

solmax

END_OF_FILE: RESULT.md
