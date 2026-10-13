# Conversation continuation — 0.24.0

## Scope

This correction connects completed setup and ordinary Work state to the native
conversation. Core remains the execution authority. Conversation actions are
derived views of existing setup, workflow, procedure and Work records. Delivery
receipts record observed context inclusion and final replies; they do not add an
execution graph or accept owner Work. Core upgrade 16 → 17 is explicit.

The ordinary assistant can read current state after a missed notice or reopening,
select the existing first Work, and explain the next step. Actual delivered owner
entries, queued inputs, extension input and history have separate origins.

## Audit corrections

- A proven unsent delivery claim can be released after session fencing. Unknown
  sends retain their evidence and cannot be released for a blind retry.
- A normally displayed question is recorded at the point it is shown; polling
  does not produce a second question.
- Publishing the first Work no longer changes the setup completion event. A
  native probe reproduced a duplicate notice before this correction.
- The native probe waits for durable Attempt settlement. Its earlier exit at
  `agent_end` could kill Pi before asynchronous completion and spoil a reopening
  check. The failed traces were retained.
- A real abrupt exit after a saved final reply is recovered only with an exact
  Core proof binding Work, Attempt, session, manifest, answered invocation and
  native final Source. The proof is rechecked in the stop transaction. Missing or
  unknown evidence leaves an addressed obstacle and permits free conversation.
- Ordinary schema-17 completion also requires the same saved final proof.
  The independent review found that the normal settlement hook initially bypassed
  this check; the correction and skipped-capture regression cover that boundary.
- Delivery completion requires an assistant-channel Source. Model memory tools
  cannot manufacture the trusted native-final flag.
- Running ordinary Work remains addressable for inspection and explicit
  interruption; it does not generate an automatic completion notice.
- Installed direct compaction after reopening exposed a manifest identity
  collision: the packet was unchanged while its persisted Attempt pin changed.
  Schema-17 identity now covers the entire exact ContextState and rendered packet.
  The legacy identity recipe and saved records are preserved. The regression
  checks before/after Attempt pins and reuse when the exact context is unchanged.

## Native gate and focused checks

One complete native gate passed: **1041 tests**, native build, hygiene, Ruff,
types, **32 import contracts**, and report structure. That full run preceded the
final abrupt-exit proof and context identity corrections. The final affected
native gate passed **62 tests** in 53.94 seconds, hygiene, Ruff, types, 32 import
contracts, build and report structure. The full count is not claimed as a test
of later bytes.

The focused checks cover exact input origins, owner-question ordering, stale
context and rights, global delivery claim, tool response versus final response,
multiple invocations, backup/restore/deletion, exact old payload preservation,
TOCTOU during proof-backed stop, unknown sends, another session, first Work
selection and separate acceptance. Explicit release tests cover source schemas
1, 2, 6, 14, 15 and 16, including retained results, acceptance and send accounting.

## Ordinary installed Pi

The final wheel passed outside checkout. All **121 installed product files**
were byte-identical to that wheel, with runtime dependencies pinned to `uv.lock`.
Native tests use Pi 1.0.4 and a localhost
provider in fictional spaces. Provider replies include raw strings. Assertions
inspect actual HTTP bodies, ContextManifest, Core receipts, native entries and
saved results before allowing continuation.

The required path includes setup, question and answer, full review, normal
completion notice, selection of the existing first Work, save without acceptance,
reopening, actual compact and reopening afterward. Separate probes check identical
queued owner messages, extension input, stale wake after session change and abrupt
exit after a saved final reply.

Observed final installed results:

| Path | Actual localhost HTTP | Observed result |
|---|---:|---|
| Create → question → answer → full review → notice → first Work | 13 | One completed notice, exact accounting, one saved output, no acceptance |
| Reopen and ask what next | 1 | Existing result and current setup remain available |
| Identical queued owner entries and extension input | 3 | Three exact owner entries; extension input cannot become an owner answer |
| Stale wake after session change | 1 initial, 0 stale | No send from the old branch |
| Exit after saved final, before settlement | 2 initial, 1 reopen | Exact proof closes the old Attempt; result unchanged |
| Failed final capture | 2 initial, 1 reopen | Execution remains active; free conversation exposes the obstacle; no false completion |
| Direct compact on reopened selected Work | 2 | Both summaries contain checked manifests and omit host wake tokens |
| Reopen after compact | 1 | Same selected first Work, saved output, no active Attempts and no acceptance |

The failed-capture native case was invoked directly through
`tools.probe_conversation_pi.missing_final_capture_probe`; the default probe CLI
does not invoke this separate failure scenario. Installed byte verification,
HTTP/context traces and final state proofs are retained locally with the native
probe reports. These are 27 localhost requests and zero real-provider requests.

Before the final checks, direct compaction failed with zero HTTP and the exact
Core code `operation_conflict`. A bounded diagnostic ruled out a provider change
and established the manifest identity collision described above. The final native
repeat and installed run both passed after the identity correction. Formatting,
one test parameter type and two probe path/settlement mistakes were corrected
during feedback runs; they are not concealed as successful initial runs.

## Review and limits

Independent bounded adversarial reviews found the concrete issues listed above.
One required read-only evaluator smoke inspected the corrected delivery, question
and completion boundaries. Its evidence is source inspection; it did not execute
tests and is not a separate binding G5 or owner acceptance.

No real provider or paid API was used in this package. Synthetic native tests
establish the named mechanisms, not universal future model interpretation.
Unknown outcomes remain in the invocation ledger even if a later state change
prevents annotation of an older delivery action. They are never inferred successful
or automatically resent. Existing owner acceptance stays separate.

Exports, Git projections, a background service, a new execution graph and
automatic personal Activity creation are excluded. Selected instance backup,
upgrade and reset evidence belongs in the private archive, outside public docs.

## Package

Wheel: `zaratustra-0.24.0-py3-none-any.whl`.

SHA-256: `754fcace908e9d4e7972d672b3c7ca902c49372186eda81510bcd80ce27cc124`.

Owner acceptance of the fresh conversational trial is pending. Next: solmax.
