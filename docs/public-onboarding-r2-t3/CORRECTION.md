# R2 T3 correction — installed replay and retained proposal continuation

call: c-solmax-zaratustra-public-onboarding-r2-t3-correction-20260914
mode: PROBA; engineering_contract: 36
failed_candidate: 37ee54153080acae02a0d8edaba4f47f3f5f6191
failed_candidate_parent: 01076ed9470202aef51f84d0561b76fa1b1c4382
accepted_t2_basis: daaafe55653c38eaefe36e468858aa68a21429d0
branch: codex/public-onboarding-r2-t3-correction

## Exact bounded changes

F1: installed `zara entry change apply` first calls the existing public continuation
preparation with no context authority. That API recovers only an exact committed
request. If it requires current context, CLI prepares and separately confirms the
existing exact ContextQuery, then prepares the request. Both branches still require
separate exact Result confirmation and the existing execution API revalidation.
No journal, receipt, authority, Core or Pack behavior changes.

F2: `proposal_pending` already has a supported proposal and now directs the user to
choose the target workspace, review the saved proposal's activation preview and
exactly confirm activation. The other four unfinished actions are unchanged. Resume
remains a read and neither retains another proposal nor activates anything.

## Reproduction

Run from this checkout with the pinned environment and a NEW output directory:

```powershell
uv sync --locked
uv build --no-sources
uv run --locked python -m tools.probe_public_onboarding_r2_t3_correction --output _scratch/t3-correction-installed
```

The development harness reuses the installed safe-change probe's locked wheel
installation and its small/project positive and refusal cases. It then runs each
CLI command in a new isolated Python process through the wheel's registered `zara`
console entry point. Product module paths must all be inside the selected installed
package. Development fixtures are explicitly exposed only to scenario setup;
they are absent from the wheel. This is an installed entry-point reproduction, not
an interactive human-terminal session or independent binding review.

Only the console confirmation seam is replaced for synthetic exact/wrong authority.
The missing-confirmation branch uses the real console adapter with closed piped
input. No product approval flag or provider call is introduced. All selected
workspaces contain fictional development inputs.

`fresh-cli/correction.json` and per-command stdout/stderr/runtime files retain:

- First apply and retry return codes, complete outputs, distinct process ids, exact
  prompted request digests and loaded product module paths. After correction both
  return 0 and identical complete receipt output; first apply confirms context and
  Result, replay confirms only the original Result request.
- The first apply adds exactly one revision and one history event. The operation id
  appears once in public history. All selected change-state file hashes stay exact
  across replay, missing/wrong confirmation refusals and public API recovery.
- Every unfinished stage (`draft`, `research_waiting`, `research_returned`,
  `proposal_pending`, `activation_pending`) is resumed twice in separate processes.
  Both reads preserve all stage-state bytes, identical output and zero confirmations.
  Inspect the retained Next line manually; tests distinguish retained-stage actions
  without freezing owner-visible wording.

Baseline observation at unchanged candidate product bytes was retained in
`_scratch/t3-correction-before-02`: first apply rc0, retry rc1 `change_applied`,
public API recovery returned the original receipt, one revision/event, and byte-stable
state. `proposal_pending` and `research_returned` both said to author/retain proposal
despite the former having a proposal. Both new regressions failed on those defects
(`2 failed in 15.92s`). The first harness run stopped on a development-only history
field lookup after observing F1; that lookup was corrected before this complete run.

## Validation and handback

The correction regression module exercises fresh CLI receipt recovery, exact separate
replay authority and retained-stage progression. Additional CLI tests independently
deny context and Result confirmation, with missing and wrong authority. Existing
creation, onboarding, process-change, Work-creation and terminal-material tests cover
the complete original T3 scope, including changed/stale refusal cases.

```powershell
uv run --locked python -m pytest tests/zaratustra/onboarding tests/zaratustra/process_creation tests/zaratustra/process_change tests/zaratustra/process_packs/test_work_creation.py tests/zaratustra/core/test_terminal_materials.py tests/tools/test_public_onboarding_r2_t3.py tests/tools/test_public_onboarding_r2_t3_correction.py -q
uv run --locked python -m tools.check --deliver
```

Exact corrective implementation/report identities and actual gate results belong in
root RESULT.md and the executor handback. HOME is solmax for a separate fresh binding
G5 against the complete original T3 claim. Manual acceptance stays pending; these
checks do not close T3 or authorize integration, T4, push or release.

END_OF_FILE: docs/public-onboarding-r2-t3/CORRECTION.md
