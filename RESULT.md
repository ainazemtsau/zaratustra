# Public onboarding R2 T1 engineering handback

## outcome

T1 is implemented at commit
`fa126a0daf0aa0f8671c04ec2209651a60158d85`; its exact parent and public starting
point is `fbca9f9e36242dbcf3410241c9178d51fb66c3d1`. Product version 0.16.0 adds
schema 8, terminal Result submission, a truthful zero-current-Work state, and exact
Process-owned material save/read/recovery without borrowing Work identity or rights.

Released Result+next behavior and serialized history remain readable and unchanged.
Finite Pack exhaustion now proposes a terminal Result instead of reporting
`process_complete`. T1 adds no general later ordinary-Work admission and makes no
claim that a Process itself is complete.

## evidence

- `docs/public-onboarding-r2-t1/PLAN.md` records the decisions for W28-W32 and
  A05-A09, the exact authority/failure boundary, the schema/history compatibility
  rule, and the T2-T7 cuts.
- Migration 8 rebuilds only `work_results` to allow a null continuation, copies every
  released row/body without rewriting it, and adds transactional Process-material
  content storage. Tests compare pre/post-migration Result rows, event rows, receipt
  rows and the parsed released history, then read the saved Result after restart.
- Terminal-result tests prove one completion/event/receipt/revision, no inserted
  Work or Artifact, the source Work durably done, `current_work is None`, exact
  receipt recovery, and restart-safe Process state.
- Process-material tests prove post-terminal save and exact content/read receipt;
  Process rather than Work ownership; fresh revision and exact local authorization;
  refreshed identical replay; changed-intent, identity, wrong-Process, stale,
  missing-authorization and changed-content refusal; and transaction rollback with
  no record/event/receipt residue.
- Construction/runner tests prove a valid exhausted finite Pack returns `None` and
  emits request 6 terminal submission, while malformed, changed-history and binding
  refusals remain errors and released continuation proposals remain request 4.
- Focused verification passed: 30 terminal/material/construction tests. Strict typing
  passed for all 108 source/tool/test files. The required bounded read-only evaluator
  smoke found no setup blocker; it is setup evidence only and not binding Direction
  G5.
- Full `uv run --locked python -m tools.check` passed formatting, lint, strict types,
  all 17 import contracts, 377 tests in 141.07 seconds, and built both
  `zaratustra-0.16.0` wheel and source distribution.
- Final `uv run --locked python -m tools.check --deliver`: PASS, including report
  structure and the same complete native verification surface.
- Execution receipt: parent Codex task
  `01a0988b-ede6-7350-9652-a64a65b38863`; executor task
  `01a09e85-b8a1-7c03-ba0a-87fd18269b78`; worktree
  `C:/my_global_workflow/7974/zaratustra`; branch
  `codex/public-onboarding-r2-t1`.

## assumptions

The existing single-Process workspace model remains authoritative for this task.
Process material is immutable metadata in the canonical mutation event with exact
bytes in the same schema-8 transaction; the Process record carries the global
revision. `current_work` means the unique `draft` or `ready` Work in that Process;
zero is normal and multiple candidates are invalid history.

The caller supplies explicit identities for continuation candidates to the existing
Pack runner even when an exhausted rule does not use them. Removing those unused
candidate inputs belongs with T2's separate ordinary-Work admission/API work, not
this compatibility-focused T1.

## cuts

No general later ordinary-Work creation, common readiness/resume prose, entry/catalog
reconciliation, onboarding composition, trusted agent asset, installer/updater,
cross-process recovery fence, fictional public release, owner/private workspace,
real personal data, provider call, external service, paid right, push, release,
Direction OS mutation, Direction G5, or T2-T7 implementation.

## cost

Nineteen implementation/test/plan paths changed in the implementation commit,
including one additive migration and one new focused test module. No new runtime
dependency or external service was added and no money was spent. Verification used
local CPU and filesystem resources only. Format/import/type feedback was corrected
before the passing full native gate.

## manual-acceptance

pending. The evaluator and automated tests use fictional local fixtures and do not
constitute owner acceptance, a binding fresh Direction G5, an independent-user
onboarding pass, or a public release.

## next

solmax

END_OF_FILE: RESULT.md
