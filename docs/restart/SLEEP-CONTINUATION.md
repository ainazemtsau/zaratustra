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

Bare native Sleep reads globally through the existing `space` selector. Its
ordinary Work is workspace-owned; reading Activity sources does not transfer
their ownership, goals, assignments or rights. There is one global continuation
lineage. Earlier Activity-local Sleep histories remain exact sources, and their
analysed boundaries are never merged or relabelled as global coverage. Global
memory/Method writes retain their current destination grants; a local correction
without its destination grant remains a targeted proposal.

The adapter validates whole lineage components before choosing their frontier.
A terminal leaf with an authoritative cancellation/control fact and fenced
generation closes that entire component, including completed ancestors. Every
old Work, result, progress, reservation and unknown effect remains unchanged;
none supplies an automatic analysed boundary for a new pass.

If no global Sleep history exists, or every validated global component ended in
explicit cancellation, the next explicit Sleep starts a new independent ordinary
Work and conversation with initial v1 progress and a current global cutoff. It
has no predecessor link and no obligation to finish the cancelled queue. Current
active global memory is pinned through the existing scoped-input selection;
progress binding preserves those exact current revisions and other mandatory
inputs. The currently chosen Method stays versioned. Reading all retained history
again does not erase previous analysis or undo successful memory changes.
Updates to pinned memory or the selected Method use the existing final staged
changes path so basis validation and changes commit atomically. An intermediate
write is already retained and can make the attempt's current-version basis stale;
a rejected later settlement neither rolls that write back nor completes the Work.

One non-cancelled completed frontier uses the approved successor path; a known
unclaimed Work is recovered, and ready/resume keeps its existing identity and
cutoff. Missing/invalid parent evidence, forks/cycles, unavailable progress,
multiple non-cancelled frontiers or an unknown claimed Attempt remain blockers.
The mere presence of a cancelled row never authorizes a fresh fallback. A local
Activity pass is not a global predecessor or global coverage; an explicitly
targeted Activity's first pass is still supported.

Only an explicit Sleep start may CAS-detach a mapping proven to refer to a
cancelled Sleep Work. Attach/reopen does not start analysis. An old ready flag,
pause or test-cap/provider error is not cancellation. Old invocations are never
automatically resent or relabelled successful/not-received. The linked
cancelled-parent restart drafts REV1 through REV3 are withdrawn; this fresh pass
uses existing operations without a restart link, protocol2 or new state store.

Child creation, initial progress CAS0, progress binding and native mapping have
separate crash controls. A crash after dispatch claim cannot trigger another
automatic dispatch. Completed-successor finite policy conserves the parent's
remainder; zero remainder creates no child/send. A fresh pass after cancellation
uses its current authorized policy rather than inheriting cancelled spend or
queue. Old reservations remain; cumulative evaluation limits are not reset.
Normal production policy remains unlimited (`None`), without a sentinel integer
or new inference cap.

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
