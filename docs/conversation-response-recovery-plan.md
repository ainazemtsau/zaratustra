# Native response recovery — implementation and audit plan

## Authority and scope

The owner authorized correction of the failed completion conversation, an audit
of adjacent failure boundaries, meaningful tests and ordinary Pi verification.
Release: 0.24.1, on `codex/conversation-response-recovery`. The implemented
candidate initially used schema 17. The owner explicitly authorized schema
17 → 18 and migration checks on 2026-10-13. The structural correction and its
affected checks are complete; selected installation followed a verified restore
rehearsal. Exact release evidence and remaining limits are in the result report.
Existing Activity, setup, Work, results, acceptance and accounting are retained.
Exports and Git projections are outside this package. Real model calls need a
fresh explicit bounded allowance; prior trial allowances are exhausted.

## Authorized structural correction

The final audit found that deleting a ContextState payload can remove the exact
Attempt correlation used by the no-send cleanup guard. Delivery accounting
itself remains, but a knowledge-only send can be missed when the domain execution
ledger has no invocation for it. This violates the no-blind-repeat authority.

Publication and personal installation were stopped for this finding. The authorized
change is an explicit schema 17 → 18 upgrade: store immutable Work, Attempt and session
correlation with each delivery; preserve it when content is removed; backfill
available legacy manifests without guessing. Uncorrelatable old history requires
an explicit unresolved-evidence path, not a space-wide heuristic. The implemented
regression deletes the manifest between an observed send and attempted no-send
cleanup and proves that cleanup is refused.

The migration distinguishes exact Attempt correlation, a manifest known
to have no Attempt, and unresolved legacy correlation. Exact backfill may use a
surviving ContextState or the same invocation's execution ledger. Deleted payloads
without either proof are not reconstructed from time, nearby records or selected
Activity. Conflicting positively supplied identity fields abort migration atomically.
An omitted optional legacy Attempt field can use the exact same-invocation
execution tuple without changing the original payload. New Attempts
cannot inherit this uncertainty. A checked migration marker records unresolved
delivery evidence on already active legacy Attempts where no-send cannot be
proved. Only no-send cleanup is refused;
reading, other work and explicit interruption remain available. Explicit
interruption makes no assertion that a send did not happen. Existing stop
operations without the optional no-send guard keep their contract; the new
guard requires schema 18 and uses immutable delivery correlation.

The checks of the candidate and their byte attribution are recorded in
[the result report](conversation-response-recovery-0.24.1-result.md). The exact
deletion, symmetric registration and legacy migration checks close this technical
finding; owner acceptance remains separate.

## Established failure

A native provider stream completed and its invocation was recorded as answered.
The persisted assistant terminal entry had no visible text. Pi neither retained
that empty terminal observation nor explained the missing answer. Delivery was
marked unknown, and the ready widget promised an explanation that had not arrived.
The prior native fixture always supplied final text and missed this boundary.

This is a common delivery contract problem. Activity readiness and conversational
delivery remain distinct facts. No domain template, keyword parser, new workflow
graph, background service or replacement model engine is introduced.

## Contract

- Retain exact visible UTF-8 bytes of supported native terminal observations,
  including empty and whitespace-only bytes, before deciding whether they prove
  a visible final. Thinking is never substituted for the visible answer.
- Pin native session/entry, invocation, manifest, outcome and stop reason through
  a typed, trusted optional Source field. Absent fields preserve old canonical
  payloads. Model memory cannot manufacture or revise host proof metadata.
- Derive response outcome and repair count from existing Core operations,
  delivery events, Sources and invocation evidence. Do not create another
  execution state, change schema-17 status constraints or reinterpret old unknown
  rows as known empty responses.
- Only answered invocation plus exact completed-stop empty terminal evidence
  permits automatic response repair. Unknown send, unavailable proof, storage,
  rights, stale bases, truncation and interruption do not permit blind retries.
- At most two automatic repairs follow the first empty answer. Every repair is
  a normal idempotent Core operation, keeps the same logical delivery and checked
  action, and prepares a fresh manifest and actual invocation. Count survives
  restart and compact. One window cannot create a competing automatic claim.
- A visible nonblank completed final is the only response acknowledgement.
  Empty or whitespace text cannot complete an ordinary Attempt either. Existing
  outputs remain saved and Work acceptance remains separate.
- Put the checked host explanation task in the actual native instruction path.
  The model explains current facts and next action with its ordinary language.
  Host turns do not impersonate owner input or start/accept a new Work.
- Expose observed delivery outcome in status and current conversation context.
  A fresh owner request can recover current facts after reopening without
  replaying an uncertain old send or requiring internal identifiers.

## Checks of independent risks

| Boundary | Required evidence |
|---|---|
| Empty, reasoning-only, whitespace final | Raw native Responses stream and saved exact terminal Source; no false response acknowledgement |
| Empty followed by visible repair | Same logical delivery, fresh checked manifest, exact actual request and accounted invocation |
| Repeated empty response | Persisted two-repair bound; no fourth send; explanation/status remains available after reopening |
| Tool call before final | Tool response is intermediate; only the later terminal final decides visible delivery |
| Length, error, abort, unknown stream | Distinct evidence; no automatic empty-response repair |
| Capture/storage/correlation failure | Failure shown and preserved; no model repeat to mask lost evidence |
| Duplicate callback/receipt | No duplicate observation, repair or provider invocation |
| Session/branch/epoch/bases/rights change | Old callback fenced before new send/effect |
| Ordinary Work ends empty | Existing results and active Attempt preserved; no completion or acceptance fabricated |
| UTF-8 and old source payloads | Strict valid text proof, empty full capture valid, old bytes/checksums unchanged |
| Backup, restore and deletion | New observation/repair links serviced; independent materials preserved |

Use a proper development-only raw Codex Responses SSE fixture through ordinary
installed Pi. Decode native request compression and use fictional credentials;
never read real authorization or patch installed product code to force success.
Inspect actual request instructions, ContextManifest, terminal native entries,
Core receipts and invocation accounting. Synthetic responses prove these
mechanisms, not universal future model behavior or health advice quality.

## Delivery order

1. Implement the typed terminal/repair contract and reproduce the missing-text
   and whitespace failures at their normal boundaries.
2. Extend Pi observation, instructions, bounded continuation and truthful status.
3. Audit the coherent correction and fix concrete findings.
4. Run one full native gate; repeat affected checks after later corrections.
5. Build and verify the wheel outside checkout through ordinary Pi and perform
   one bounded read-only evaluator smoke. Record failed checks and evidence limits.
6. Request a fresh bounded real subscription trial only if it is needed to check
   the model's response to the actual instruction path. No paid API fallback.
7. Publish checked shared code to the authorized public destination. Selected
   installation requires Pi shutdown and verified backup; preserve the current
   personal Activity and Development. Instance details stay private.

Owner acceptance remains separate. Next: solmax.
