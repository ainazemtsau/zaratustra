# Ordinary execution selection — 0.25.3

## Status

The owner-approved [common transition](ordinary-work-selection-transition-plan.md)
is implemented and checked. Core schema remains 18. The finished wheel was tested
outside the checkout with ordinary Pi 1.0.4 and fictional localhost providers.
Authorized private backup, restore verification, installation and addressed repair
are complete; operational details remain private. Product commit
`0f83cdef1b86006b728d9dcba350a1b2a02aa947` is published in
`ainazemtsau/zaratustra/main`, verified through authenticated GitHub and fetched
Git readback. Finished-result owner acceptance is separate.

## Cause and correction

An ordinary Work selection replaced the current Work and cleared its Attempt
pointer before settling that Attempt. The old execution still owned the exclusive
directory. The next context correctly refused with `resource_busy`; the previous
resource-creation correction addressed a different failure.

Work selection, native commands, project changes and assigned launches now share
one guarded transition. Its actual native entry binds owner input, invocation,
manifest and target. Core rechecks rights, revisions, epoch, inputs, resource and
both send journals in the interruption transaction. The host commits a rechecked
target only after the exact receipt. Work, outputs, history, cost and acceptance
remain unchanged. Assigned execution detaches ordinary selection; the main agent
remains the conversational coordinator while the executor owns its resource.

Same-Work assignment derives from the surviving fingerprinted interruption
receipt, never from no-send cleanup. Complete publications and older unpublished
assigned answers retain their admission precedence. Historical resource pins
prove interruption; current assignment separately validates its resource policy.
An idle mode change is valid with the same active identity and normalized root.
Root change and revocation still refuse automatic handoff.

Native pending/committed entries survive closure. Startup is passive. Initial
selection, addressed continuation and cancellation share request recovery, so a
lost committed reply preserves the original choice and receipt in the same Pi
and after reopening. Old-batch tools cannot write with an implicit new selection.
Read-only inspection has an exact manifest reference and creates no execution.
No new graph, queue, service, schema, domain template, intent parser, weakened
exclusive resource or automatic owner acceptance was introduced.

## Core, static checks and audit

- The frozen 0.25.2 negative native trace reproduced refusal after two accounted
  localhost requests, before target HTTP. All 124 production files matched its
  supplied wheel. It is failed-path evidence.
- Native feasibility established actual pre-tool entry identity/accounting.
- Core regressions cover exact interruption, races, changed rights/session/epoch,
  pins, unknown and deleted-manifest sends, reserve, deletion, restore and current
  targets. Published-output and previous-unpublished-output precedence are tested.
- One bounded independent read-only evaluator identified resource-policy revision
  and continuation transport-loss gaps. Both were corrected and read again with
  no new concrete finding. This source review is not independent runtime proof.
- Three public-operation policy regressions failed before correction, then passed:
  mode change can assign; changed root and revocation refuse without an effect.
- The full `tools.check --deliver` run passed hygiene, format, Ruff, mypy and all
  33 boundaries, then reported **1287 passed, 1 failed**. The failure matched an
  obsolete error sentence; the intended `recovery_required` refusal occurred.
  Its test now checks the stable code and exact unchanged execution. The full
  run is not labelled green.
- Affected repeats passed through `tools.check --files`: **81 Core tests** and
  **75 Pi tests**, including static checks, boundaries and package builds.
  Affected native-probe formatting/Ruff/mypy also passed. Earlier test typing
  errors and a local variable type collision were fixed before these repeats.
- A checkout SDK UI trace checked assigned/composite/closed Work inspection,
  addressed answers and passive recovery-obstacle restoration with zero sends.

## Final installed ordinary Pi

All 125 production files matched the final wheel byte for byte. Runtime
requirements came from uv.lock; the installed product was imported before the
explicit development harness. Native processes ran outside the checkout.

| Scenario | Actual localhost HTTP | Observed result |
| --- | ---: | --- |
| Ordinary A → B, output and reopen | 6 | Correct pins; exact A interruption before B; outputs preserved |
| Registered external project and stale write | 6 | File in target root; old-batch write refused; reopen preserved |
| Ordinary A → another assigned Work | 3 | Saved question; parent detached and settled |
| Ordinary → assigned execution of the same Work | 3 | Exact receipt; one assigned execution; free parent |
| Lost initial reply, reopen, lost continue reply, same-Pi retry | 4 | Original receipt reused; one target Attempt |
| Lost initial reply, reopen, lost cancel reply, same-Pi retry | 4 | Original receipt preserved; no target Attempt |
| Full setup from an existing selected Work and later continuation | 55 | Whole path and exact accounting completed |
| **Total final installed traces** | **81** | **No real model calls or automatic acceptance** |

The full path includes two questions, confusion without closing a question,
answer after reopening, raw malformed JSON, invalid operations, two format
corrections, full review, multi-part correction and another full review,
activation, procedure file placement, two compaction requests, typed output
correction, reopen and preservation of a pre-upgrade fictional Work. Schema
15 → 18 and existing Activity structure adoption were exercised. Six internal
stage originals had exact protocol bytes and capture/account/publication order.

Loss probes withheld actual committed replies, without fabricated effects. The
second loss was retried in the same Pi using repeated tool IDs in different
native entries. Actual sends, manifests and receipts were independently read.

## Failed trials retained

- The first assigned candidate incorrectly demanded Attempt correlation for free
  conversation. That assertion and a real shutdown-diagnostic scope mismatch
  found there were corrected before the final installed repeats.
- The first extended setup provider confused a selected ordinary Work with an
  internal stage. It failed at ten requests rather than nine in that segment;
  saved Core showed ready setup and one unknown ordinary reply. That space was
  retained. The corrected provider routes exact current stage Work addresses,
  retains failure requests/events, and passed 55 sends in a new fictional space.
- A transport-loss fixture initially omitted its intentional fetch error from
  the expected error count. Final installed loss traces each observed that one
  expected error; product effects were not replaced by the fixture.
- Initial Temp/cache sandbox refusals were rerun with required host access.
- An extra Git-blob versus wheel byte comparison found the pre-existing empty
  `py.typed` marker as LF in Git and CRLF in the Windows checkout/package. The
  other 124 product files matched exactly. This is not reported as a 125-file
  Git byte-equality pass; all 125 installed files do match the tested wheel.
- The private backup probe initially expected backup inventory to be unchanged.
  Its verified copy was retained and resumed. Only documented backup tables may
  differ; domain histories were checked separately on restore and final readback.

These trials are not counted as successful final traces.

## Artifact and delivery

- Version **0.25.3**, schema **18**.
- Wheel: `dist/zaratustra-0.25.3-py3-none-any.whl`.
- SHA-256: `f8a527e98e7686834388c73396aeb7bb3ca527655354c5c5e7648a85df94bad8`.
- Final package build equals the frozen installed-test wheel.
- Private maintenance preserved Activity/Work histories, originals, results,
  delivery/invocation accounting and acceptance. Only the exact execution left
  by a closed old Pi was interrupted through the public owner operation.
  Installation alone changed no Core state. No real procedure/model was run.
- Public destination: `ainazemtsau/zaratustra/main`, product commit
  `0f83cdef1b86006b728d9dcba350a1b2a02aa947`, verified after push. This reporting
  update changes no product or wheel bytes. Private Git and exporters were not
  updated.

## Limits and acceptance

Local fictional providers prove native execution, preservation and admission;
they do not establish semantic quality for every future conversation/provider.
The full suite was not rerun after affected corrections; its failed complete run
and passing affected repeats are reported separately. Localhost socket-reset
diagnostics at native closure were retained; they are not extra provider sends
or Work acceptance. Subscription/paid API calls: **0**. Owner acceptance of the
finished release remains unrecorded.
