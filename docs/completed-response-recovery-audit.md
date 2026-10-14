# Completed assigned response after pause — approved recovery contract

## Confirmed interruption case

The one-conversation-owner candidate preserves ordinary foreground execution,
but native interruption testing found a separate unresolved recovery contract.
The test used an ordinary installed Pi and a held localhost assigned response:

1. Start an Activity draft and hold its provider response.
2. Abort the ordinary foreground tool.
3. Observe the committed pause and stop request before releasing the response.
4. Release a complete draft while the assigned process is stopping.
5. Observe truthful `answered` accounting, a complete original Source, stopped
   assignment and interrupted Attempt, but no published output Artifact.

There is no data loss or acceptance in this trace. The problem is subsequent
continuation. Public status advertises `can_resume=true`. Core resume admission
and the coordinator guard exclude admitted/sent/unknown invocations, but do not
handle an answered invocation without its output. Dispatch would assign the
same stage a fresh Attempt. No second provider request was made by this audit:
the saved public state and permitted dispatch path were inspected before it.

The retained assigned Source has full content, scope and session, but no exact
native terminal/invocation/manifest proof. The public terminal reader refuses it.
Matching text, Work or session cannot substitute for missing producer evidence.

## Owner-approved general contract

This applies to Activity setup, ordinary workflow and procedures.

### Receive a completed response

Record the exact completed assigned native response before interpretation or
output application. Retain its native entry, invocation, manifest, output
protocol and original bytes. Receiving an answer is distinct from completing
Work, publishing its output or accepting it. Pause and stop fencing must leave
the observed answer and truthful accounting available.

### Derive the next action

Derive it from exact existing execution and response records:

- Unknown send: inspect the outcome; do not resend automatically.
- Proven completed response without applied output: recover/validate that answer.
- Proven failed or rejected response: follow its saved authorized correction.
- Missing association: show an addressed saved obstacle, with explicit owner
  material admission as a possible legacy path.
- No response or send: the ordinary execution admission decides whether a launch
  is permitted.

An answered invocation without output must never silently become a fresh
generation request. This is execution recovery, not conversational message
delivery or duplicate-text suppression.

### Validate and continue without false producer proof

Use a trusted idempotent Core recovery operation over the exact retained reply.
Recheck current rights, pinned inputs, declared result protocol and exact bytes.
Recover an Artifact with honest provenance from that reply; do not publish it
as if an interrupted Attempt had succeeded or a new model had generated it.

Use the existing WorkPlan and internal validation mechanism for a fresh actual
validation/recovery execution where needed. Preserve the stopped original Work
and Attempt as history. Specify the exact admissible producer proof and plan
transition before implementing this operation; a copied output or rewritten
old Attempt is not an acceptable implementation.

Setup/workflow re-review the complete current proposal before application.
Procedures additionally inspect real operation receipts and entries before
claiming effects or completion. A completed response alone proves neither.
The root publishes its own result through its actual current Attempt; owner
acceptance remains separate.

### Compatibility and maintenance

Existing uncorrelated Sources remain historical originals. Do not synthesize
terminal proof or rewrite their accounting. Check restored epochs, deletion of
bases, changed inputs, repeated recovery receipts and conflicting responses.
Recovery must survive restart, compact and repeated delivery without another
model send. No second execution graph, journal or status authority is added.

Schema 18 already has response metadata and immutable send correlation. Whether
the required recovery authority and proof need further schema changes must be
established during the contract review, not assumed here.

## Required regression evidence

- Completed response before/after pause and stop, including whitespace, malformed
  JSON and late error: exact original and truthful outcome survive.
- Restart at capture, validation and output-application boundaries: no repeated
  model generation, no repeated operation effects or acceptance.
- Same stage with changed inputs: preserved historical reply and explicit
  re-evaluation; no application to a different version.
- Setup, general workflow and procedure: same public recovery contract with
  correct domain validation and actual producer proof.
- Legacy uncorrelated response: concrete obstacle or explicit owner material
  admission; no fabricated proof and no automatic replay.
- Ordinary installed Pi: abort, late answer, close, new owner request, recover,
  review and first Work, with HTTP/ContextManifest/receipt checks.

## Implementation

The owner explicitly authorized this contract. Schema 18 is sufficient: no
DDL, migration, second graph, delivery ledger or queue was added.

`RecoverAttemptOutputRequest` checks the exact native terminal Source, immutable
invocation/manifest/session correlation, saved protocol, current Work revision,
rights, input and resource pins. Its receipt creates a proposed Artifact with
protected `RecoveredResponseProof` and exact Source/manifest dependency edges
in the existing knowledge-basis index. It links through ordinary Core output
admission. It never rewrites an interrupted Attempt, emits a normal successful
publication event or accepts Work. Composite root output still needs its own
genuine execution proof.

Setup, workflow and procedure coordinators call the same derived response view
before dispatch. They validate recovered bytes through their existing domain
contracts. An answered original without sufficient terminal proof is an
addressed obstacle. Unknown sends in earlier generations cannot be hidden by a
later no-send Attempt or an older linked output. Fresh assignment is fenced at
Core, independently of coordinator behavior.

A publicly linked proposed output remains available through existing output
authority; availability does not claim that an assigned response was consumed or
that its Attempt succeeded. Fresh assignment still requires exact publication or
recovery evidence for earlier answered invocations. A genuine first publication
in a multi-slot Work yields `partial_output`, allowing its remaining slots to
continue without reopening an unresolved send. Generated Artifact identity is
checked against its actual operation event and receipt, never used alone as
producer proof.

The assigned native adapter retains original bytes before finish accounting,
then captures the exact persisted native entry at `turn_end` before parsing or
publication. The earlier event lacks a persisted entry ID and is honestly kept
as a raw original, not given synthetic terminal proof. A crash between these
captures therefore preserves data but requires inspection instead of replay.

Read-only public status exposes these derived outcomes. Source/manifest deletion
services recovered copies through the existing dependency mechanism. Restored
incomplete replies from an old epoch remain historical obstacles; already
recovered outputs and their history remain readable. Copying recovery is limited
to simple Work with one supported text/typed JSON slot; Method/composite results
require their genuine producer and ordinary validation proof. Unsupported or
legacy unproven contracts yield an addressed obstacle instead of a new send.

## Status

Implemented and published in the common 0.25.0 product, source commit `881958e`;
actual delivery checks are recorded in the release report. Owner authorization
is distinct from owner acceptance. Personal installation was not performed.
The separate SQLite contention observation is not established or declared fixed.
