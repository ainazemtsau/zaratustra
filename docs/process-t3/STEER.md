# HOME technical feedback for T3 — not owner words or a new approval

Continue the approved T3 CALL. This is an in-session HOME pre-pass, not binding G5.
Preserve other work; resolve this note using current source and meaningful checks,
then retain it under docs/process-t3/ before clearing root STEER for native gates.

## Reproduced ordinary continuation defect

Current `_lineage_from_history` compares the whole current Work record with the
`event.next_work` birth snapshot. A legitimate later Work mutation changes revision
and scope, so that equality rejects valid lineage.

HOME ran only public product operations in a NEW fictional workspace: the existing
construction fixture commits Work 1 and creates Work 2; a catalog entry anchors
Work 1; `prepare_process_change` succeeds for actual Work 2; supported local
`authorize_artifact` on Work 2 changes scope from `work_metadata` (revision 8) to
`work_metadata_and_artifact` (revision 9); the next `prepare_process_change` refuses
`lineage_invalid: Continuation record differs from history`. The failed query leaves
records unchanged. This is normal functional workflow, no state edits or access bypass.

Script: C:/my_global_workflow_worktrees/solmax/.tmp/constructor-execution/check-t3-lineage-prepass.py.
Evidence: `_scratch/process-t3-home-lineage-prepass-c262fb7cdcc04bd2b67a31fc079a6b9b/result.json`.
Re-derive the proper committed-link/identity invariant while reading current Work
from current Core; do not relax it into timestamp guessing or ignore broken links.
Verify ordinary mutation and multiple completed continuations, not only the first
new Work in its unmodified birth state.

## Two related continuation questions to verify in your in-progress implementation

1. A transitioned next Work pins the projected edition-2 basis SHA, whereas the
   preceding accepted artifact remains the required unchanged edition-1 snapshot.
   `_basis_snapshot` currently searches authorized artifact content for that exact
   SHA only. Verify an ordinary subsequent review/continuation on the new Work can
   obtain its exact effective basis through supported product operations and saved
   grounds; do not require rewriting the previous artifact or hand-editing state.
   Also distinguish one pending change at a time from a permanent one-change limit:
   after the first effect, a new explicit reviewed intent must not remain blocked
   forever merely because `journal.approved` retains the earlier applied transition.
2. Current `prepare/review_process_change` appear transient until approve/reject.
   Verify how an understandable proposal awaiting a decision is saved/discovered
   in another chat through the shipped tool surface. Distinguish that stage from
   approved intent awaiting Core effect, and retain the original CALL's resumability.

These questions preserve the approved outcome and are not a selected schema or new
owner migration policy. Record evidence or a precise unresolved limitation; do not
claim a product behavior from the plan alone. No new owner confirmation is needed
for this bounded technical correction.

END_OF_FILE: STEER.md

