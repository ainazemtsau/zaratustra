# Verified Sleep continuation

This additive Core/app0.3 contract implements the owner's approved proposal
SHA256 `7c5c9f329da56d7db0350277b5111971ca9d33892c80c250beb646be1f1765f9`.
The [authority and exact proposal](../../evidence/permanent-use/continuation-proposal/OWNER-APPROVAL.json)
are retained. Mechanical checks do not establish semantic adaptation or owner
acceptance. Overall readiness remains pending exact-package review and live/gate
checks.

The existing `open_work` operation accepts optional `continuation_from` with
`attempt_id`, `result_hash`, `work_revision` and `basis_refs`. `result_hash` is the
existing final-result fingerprint. The parent must be completed with its latest
Attempt finished, exact final result and no unresolved dispatch/tool actions.
Admission checks the current parent revision and current basis heads. The admitted
link then freezes their exact revisions. There is one successor slot shared with
the existing `next_work` mechanism. Concurrent commands cannot create two children;
the original command replays its exact receipt.

`sleep-progress/v2` adds `predecessor_ref`, `transition` and `range_start` to the
existing progress shape. Completed Work/result and v1 records are never reopened
or rewritten. In `same_window`, the child preserves the predecessor's cutoff,
range, enumeration and honest remainder. Selected-but-unanalysed sources remain
in that remainder. Delivery, analysis and applied receipts belong to their original
Work; inherited proof is followed through exact lineage, not relabelled as the
child's evidence. In `new_window`, the predecessor must prove enumeration through
its cutoff, no remainder and valid declared analysis coverage. The next range
begins after that boundary, including later arrivals without re-enumerating all
history. Analysis remains the model's explicit declaration; no finding is forced.

The native adapter follows the unique eligible completed checkpoint, or recovers
its known unclaimed child through Core. Several eligible checkpoints, a missing
predecessor, unavailable progress or an unknown claimed Attempt require explicit
reconciliation. Cancelled historical roots remain visible with no analysed-boundary
credit. They do not prevent following a unique completed checkpoint, do not become
resolved effects, and never authorize resetting an established Activity to zero.
Only an Activity with no established eligible Sleep checkpoint/lineage starts an
initial range at zero; an existing ordinary Activity's first Sleep is supported.

Current limitation: a cancelled-only Sleep history or a cancelled successor can
leave no eligible public continuation. Cancellation preserves old fences and
uncertainty; it does not itself supply a completed checkpoint. A separate proposed
cancelled-parent restart contract is not implemented in this version. Do not treat
the completed-successor checks as proof of general cancellation recovery.

Child creation, initial progress CAS0, progress binding and native mapping have
separate crash controls. A crash after dispatch claim cannot trigger another
automatic dispatch. Finite optional resource policy conserves the parent's
remainder; zero remainder creates no child/send. Normal production policy remains
unlimited (`None`), without a sentinel integer or new inference cap.

Data protocol1 uses the existing SQLite `user_version` plus durable matching audit
and receipt, without another table or sidecar authority. New roots initialize
protocol1. Core0.3 reads admitted protocol0/v1 data; v2/late succession requires1.
`prepare_update` holds the existing OS exclusion, verifies a pre-upgrade snapshot,
then atomically publishes the marker and audit. All existing IDs, immutable bytes,
history, refs and credentials remain. Old Core0.2 rejects protocol1 before mutation.
If the process stops after that transaction but before runtime selection, the
verified new package can finish publication without downgrade, init or replay.
The package manifest advertises required protocol1 and readable protocols0/1.

Historical proof traversal is iterative, with cycle detection rather than a hidden
recursion-depth lifetime limit. Existing default `open_work`, original `next_work`,
v1 bytes and receipts retain their meanings. Core still protects its own records;
ordinary Pi filesystem/shell observations are not exactly-once Core transactions.
This change adds no content migration, server, synchronization or backup setup.

END_OF_FILE: docs/restart/SLEEP-CONTINUATION.md
