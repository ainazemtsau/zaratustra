# Entry T4: recoverable exact material transfer

## Bounded outcome

This increment extends the existing incoming-material coordinator; it does not add a
second intake or change Core transactions. One confirmed transfer still performs the
ordinary `publish_artifact` operation followed by the ordinary `accept_handoff`
operation. A coordinator journal and one stable per-intake advisory lock make those
two separately committed stages recoverable across lost replies, restarts and
cooperating retries.

The journal lives below the selected workspace's existing `inbox/transfers` tree. It
contains the exact canonical preview, input hash and any receipts already returned by
Core. It contains no authorization token or assertion that can grant authority. A
bounded inspection API discloses only the intake identity, immutable preview hash and
claimed stage names, explicitly labeled unverified; receipt bodies and incoming
material are not disclosed by that no-confirmation surface.

## W12 — original basis, derived stages and recovery

The ORIGINAL intended basis is the envelope's immutable workspace, Process, Work and
Artifact identities, source revision, exact Artifact-version basis, new bytes and
hash, provenance, operation identities, and the Work's observed Artifact revision and
Pack binding in the confirmed preview. Publication is valid only at that original
revision. Acceptance is valid only at `original revision + 1`, the revision produced
by this transfer's exact publication receipt. Neither request is rebuilt with the
latest revision.

Before the first Core effect, execution atomically saves the exact plan. After each
returned or post-projection-error receipt, it atomically replaces the journal with
the added stage. A missing or stale stage claim is not success: under the same
trusted confirmation, recovery uses authorized public Core receipt lookup, compares
the receipt with the exact operation fingerprint and expected revision pair, verifies
the registered publication bytes, and verifies the accepted Handoff. A malformed
journal, changed input under its intake identity, mismatched stored receipt or
receipt/record collision is refused.

The exact original plan is necessary for recovery. If the whole journal has been
lost after the source revision advanced and the original publication identity is
present, preparation refuses with `progress_unavailable`: it cannot reconstruct the
original preview from current active Artifact or Work facts. This is distinct from a
lost response or a missing/stale stage receipt while the exact plan remains journaled;
those recover from authorized Core receipts. With no journal, no Core effect, and a
genuinely current initial basis, preparation remains an ordinary valid new start.

The lock covers authoritative rediscovery, validation, any remaining effect and the
journal update. Thus cooperating local callers using this coordinator cannot create a
second stage. The guarantee does not cover hostile writers, manual journal changes,
network filesystems or non-cooperating direct Core callers. SQLite and immutable-file
rules remain Core's existing local guarantees.

An unregistered exact Artifact file left between physical publication and DB
registration is not a committed publication. With no Core receipt and the original
revision still current, the ordinary Core retry may reuse those checked bytes and
perform the one registration/event/receipt. The coordinator never calls it accepted,
deletes it or claims a spanning rollback.

## W15 — accepted material, Result and continuation

The saved transfer receipt always retains the original publication and acceptance
receipts plus `completion: not_requested`. At acceptance revision the saved
continuation is the same ready selected Work. Receiving material never completes the
Work, creates a Result or creates a next Work.

Recovery also reports current state separately from that immutable saved transfer
fact. If the selected Work is still ready, it reports the current ready revision. If
it was later cancelled, it reports that terminal fact. If it was later completed by
the standard `submit_result` operation, it reports `saved_result`, the exact Result
operation and next Work identity obtained through the current authorized basic
Process read. It does not reopen or resurrect the terminal Work. Current receipt and
continuation disclosure remain subject to current metadata rights; revocation
refuses recovery rather than leaking journal receipt bodies.

## Confirmation and faults

Every invocation that may inspect authoritative receipts or run a remaining effect
requires a new process-local trusted authorization bound to the complete canonical
intended plan and selected workspace. Persisted data cannot mint it. A fresh trusted
session can review the same plan and resume. The no-approval inspection sees only
unverified coordinator stage names.

Automated checks inject failures before publication, after an exact file but before
registration, after publication commit before journal persistence, between stages,
after acceptance commit before journal persistence/final response, and during both
post-commit projection rebuilds. Fresh preparation/restart tests prove one Artifact
version, one publication event and one acceptance across repeats. They also cover
changed content/target/basis under an old identity, a stale original revision,
terminal Work, malformed/colliding progress, missing stage receipts recovered from
Core while the original plan remains journaled, complete-plan-loss refusal,
current-rights refusal, later standard Result continuation and cooperating threads.

## Public boundary and limits

The package exports preparation, trusted authorization, execution and bounded
progress inspection from `zaratustra.intake`; the existing `zara entry intake`
command uses the recoverable execution. A new generic installed-wheel probe creates a
new schema-7 workspace and ordinary authorization from an unrelated directory, loses
stage replies, restarts, repeats the exact envelope and verifies the saved current
continuation.

This is not an all-or-nothing transaction, Core status, authority or Pack-binding
redesign, Process constructor, provider integration, external-chat proof, automatic
research, Work completion, UI, memory/model routing, hostile same-user sandbox,
power-loss certification, paid service or CI feature.

END_OF_FILE: docs/entry-t4/PLAN.md
