# Ordinary Work selection transition — approved correction

## Status and authority

Prepared after the owner reproduced another ordinary Pi refusal in installed
0.25.2. On 2026-10-15 the owner approved the common transition described here.
Implemented as 0.25.3; actual verification and its limits are recorded in
`ordinary-work-selection-0.25.3-result.md`. This plan is not release evidence or
owner acceptance of the finished package.
No personal data, real instance identifiers or operational receipts belong here.

Existing Core schema 18, single conversational ownership, exact invocation pins,
and separate Work acceptance remain authoritative. Exports are outside scope.
The previous resource-creation correction remains; this failure has a different
cause. Personal Activity and Development are preserved, not recreated.

## Confirmed failure

1. A normal user request begins in selected ordinary Work A, creating Attempt A.
2. Its model asks to select existing Work B on the same exclusive directory.
3. `use_existing_work` checks B, then changes bridge selection to B. The extension
   replaces its selection and clears the local Attempt pointer.
4. Attempt A is still active. The next provider context tries to start B and
   correctly receives `resource_busy` before HTTP.
5. Later cleanup addresses B, so it no longer owns the pointer needed to settle A.

The resource exclusivity check is correct. A selected Work is not itself proof
that the departing execution has finished. No natural-language parsing is needed.

The earlier installed probes selected B from a free conversation. The later Core
handoff regression explicitly interrupted A before assigning B. Neither tested
selection while A remained active in the same native owner response. This was a
coverage gap, not evidence that this transition worked.

### Addressed native reproduction

An ordinary Pi 1.0.4 negative probe now reproduces this exact transition. It used
checkout-native code whose 124 packaged production files equal the frozen 0.25.2
wheel, not a claimed new isolated installed-wheel success. Two localhost requests
were answered and exactly accounted. Publishing A's proposed output completed
its producer Attempt through the existing publication path; the following request
started another ordinary Attempt on A. Selecting B abandoned that current pin,
and starting B then refused with `resource_busy` before a third HTTP request.

The second A Attempt remains active; B has no Attempts/invocations and is exactly
unchanged. The proposed original is intact, all actual requests match their exact
ContextManifest/delivery/Attempt/native-session pins, and neither Work is accepted.
The bounded probe intentionally stopped at the failing context boundary, not at
native settlement. It returned a reproduced-failure report, not fulfilled Work.

Earlier harness attempts failed before this reproduction: missing test dependency
in an isolated production environment, sandbox/cache admission, mismatched fixture
provider, wrong fixture model replacement, and an incorrect assertion that output
publication leaves the producer Attempt active. The last assertion caused five
localhost requests through native HTTP-500 retries; that failed report is retained
and is not product proof. The corrected bounded probe made two localhost requests.
No real subscription or paid API requests occurred.

## Native ordering

Current Pi's awaited `message_end` accounts the response before its tools run.
`turn_end` accounting is fallback. Exact persisted terminal Source evidence is
retained at `turn_end`, after the tool batch. A response requesting tools does
not prove final completion. The correction must preserve this distinction.

An assigned procedure introduces an important boundary: `zara_data.run` launches
its coordinator before waiting for the process result. Keeping an ordinary A
Attempt blocks assigning B on the same root; selecting B ordinarily first also
blocks assigning that same B. This source-confirmed adjacent case is not claimed
as another executed reproducer. Stopping A while keeping ordinary selection A is
insufficient: the next context could reacquire A while B's RPC waits for input.

Do not defer every transition to `turn_end`: an awaiting lifecycle tool could
then wait for a result whose execution requires that very deferred transition.
Use the supported pre-tool boundary with the actual completed native response
and tool-call identity. Persist an honest typed host observation there,
without inventing a native session entry ID or calling it final reply proof.
When a real persisted terminal Source already exists, reuse that exact evidence.

A bounded native feasibility probe established this checkpoint in Pi 1.0.4:
one process, two localhost requests, no real model calls. `message_end` already
accounts the response, but the current assistant entry is not yet in its branch.
At `tool_call` the persisted assistant entry exists before tool execution and
matches the later terminal entry. Thus existing native terminal observations can
retain real identity without inventing an entry or requiring a final reply.
Tool IDs alone are not globally unique; bind the current entry and invocation.
Retain that exact Source once and reuse it at `turn_end`, where additional tools
may already have changed the exposed-reference set.

## Intended user experience

The user says to continue another saved task. The coordinator selects it and
continues using retained data. There is no manual unlock, internal identifier,
second questionnaire or ordinary-save confirmation.

If execution provenance or a send outcome is genuinely unresolved, the assistant
explains that precise obstacle. It does not claim success or silently retry.

## One shared transition

Use the same host-owned transition for `use_existing_work`, `/zara-work`, project
changes and ordinary-to-assigned execution. Do not retain separate snapshot-based
automatic-stop policies. A target identifies execution mode as well as Work/root.

1. Validate the target and bind the real consumed owner Source. A native command
   or UI choice retains its actual owner input; it cannot borrow the latest chat
   message or create an assistant-authored user message. Retain the exact
   departing Work/Attempt/session/epoch and requested target. Selecting the same
   ordinary Work/resource preserves the current valid Attempt; delegating that
   same Work to an assigned executor is a real ownership change.
2. During a native tool batch, stage the target without replacing the departing
   selection or clearing its Attempt. Persist the exact pending choice using
   native session entries, alongside existing committed-selection entries. This
   is a saved host choice, not a second execution graph or status authority.
3. Fence subsequent effects in that batch, including native file/command tools,
   against an implicit selection change. A tool cannot write to A while assuming
   it already selected B. Core and host admission enforce the same boundary.
   Use Pi's existing sequential tool execution mode for selection transitions;
   previous tools finish before staging and later tools cannot overtake it. Do
   not add a separate tool queue or change worker-node parallel execution.
4. At the supported native response/tool boundary, finish accounting and retain
   the exact native observation against its original invocation/ContextManifest
   pin. Verify the requested target and native call/owner choice belong to the
   current host branch/generation. Before changing product behavior, a feasibility
   probe must establish that evidence exists before a lifecycle tool needs to
   launch; ordinary final-proof admission must not be weakened to obtain it.
5. Interrupt only the exact departing ordinary runtime Attempt using the guarded
   Core operation below. Keep its Work proposed, outputs and history unchanged.
   Do not mark it completed, cancelled, succeeded or accepted.
6. Commit the target selection only after the operation receipt is known. Drop
   the old local pin after its disposition is known. Before the next provider
   request, build a new target ContextManifest and start the target's own Attempt.

For an assigned target, detach ordinary execution selection instead: the main
agent remains the free conversational coordinator while the existing assigned
Pi/DBOS executor owns B. Keep its addressed process separate from ordinary Work
selection. Await its actual ProcessBoundary through the existing lifecycle tool;
do not reacquire A or start an ordinary B Attempt while the assigned RPC waits.
New context explains the actual result/question. No callback injects another
completion conversation, and no extra model request is needed just to hand off.

When no old Attempt exists, ordinary selection uses the same validation and
commit path without inventing an interruption. Assigned/composite execution
continues to use its existing coordinator, not this ordinary transition.

## Guarded Core interruption

Add an optional typed transition proof to existing `StopAttemptRequest`, checked
inside its normal transaction. Existing explicit owner interruption retains its
meaning; the stronger guard applies to automatic selection transitions.

Bind the proof to the actual owner Source/choice, exact retained native response
or terminal observation, real tool-call/entry identity for its evidence kind,
invocation and ContextManifest, departing Work/Attempt/session/epoch and
revisions, and exact requested execution target. Native UI choice and a model
tool selected for a consumed owner request retain distinct provenance. Reuse
native correlation/rights checks; the model cannot supply trusted host evidence
by writing prose or a flag. An early observation proves a safe interruption
boundary, never final completion or delivery of a human-facing answer.

For a handoff of that same Work to an assigned executor, derive an addressed
handoff outcome from the checked interruption receipt. An ordinary tool-use
response is not an unpublished assigned final. Carry the exact receipt into
automatic assignment and recheck it there so deletion cannot authorize a fresh
launch. Keep legacy explicit owner interruption and assignment contracts; absent
optional transition fields preserve their former canonical requests.

The resource revision at interruption remains an exact historical pin. A later
assignment validates its own current resource revision and rights. A legitimate
idle policy revision does not rewrite that historical proof; reuse still requires
the same active resource identity and normalized directory. Changing or revoking
that directory invalidates automatic same-Work handoff.

Atomically refuse a changed owner/pin/epoch, assigned execution, an incompatible
wait, unavailable proof, uncertain legacy delivery correlation, or any unresolved
send/reserve for that Attempt. Check both execution and durable delivery evidence;
a deleted manifest must not conceal a send. A race after a host snapshot cannot
turn an automatic switch into the existing explicit interruption of unknown calls.

This proposes no new table, graph, queue, service or schema upgrade. Optional
defaults must remain absent from old canonical request JSON. If implementation
shows existing storage cannot retain required evidence, stop before changing the
schema and present the concrete missing relation for approval.

## Failure and recovery

- If validation or proof retention fails before interruption, preserve A and
  refuse the switch. Do not discard its local/durable identity.
- If A was interrupted but target commit fails, retain and recover its exact
  receipt. Expose the target obstacle with a usable conversation; do not leave a
  local pointer pretending A is active or report B as running. Core interruption
  is atomic, but the whole Core/config/native-session transition must not be
  advertised as one shared database transaction.
- Repeated callbacks/delivery use stable request identity and existing receipts.
  They cannot create another Attempt or provider send.
- Initial selection, addressed continuation and cancellation use the same native
  request-recovery boundary. Losing a committed reply preserves the original
  pending choice for explicit retry in the same Pi as well as after reopening.
- Close after staging retains the requested target and exact old address.
  Startup inspects it passively. Continue from the checked receipt/proof after
  real owner input; missing proof or unknown sends remain an addressed obstacle.
- `/new`, branch/tree/fork changes and generation fencing invalidate callbacks,
  not historical receipts. Do not interpret restored messages as new owner input.
- Backup/deletion maintenance covers the retained addresses and native entries.
  A deleted owner/proof Source cannot authorize replay or a new dispatch.

## Checks before delivery

Start with a bounded ordinary installed Pi reproducer: select A at boot, retain
a proposed output, then select B in the same request on one exclusive root. Read
actual requests, manifests, invocations and terminal Sources. Record the failing
baseline before changing product behavior. Use fictional data and localhost only.

Extend existing tests for these independent risks:

| Case | Observable result |
| --- | --- |
| Same-turn A to B on one root | A's exact interruption precedes B; each send has the proper pin; proposed output/accounting survive |
| Same target or duplicate callback | The valid Attempt remains; no extra Work, interruption or send |
| More tools in the selecting batch | No effect uses an implicit new selection or stale native tool root |
| A send changes after host observation | Core transaction refuses automatic interruption; no unknown outcome hidden |
| Project selection and command selection | Same guarded transition and actual resource root |
| Ordinary A to assigned B, including same Work | The coordinator relinquishes execution, the assigned process owns it, and its saved question does not restart A |
| Wrong session/rights/epoch/proof or assigned wait | No unauthorized stop or switch |
| Close before/after interruption, lost receipt, target refusal | Exact continuation or explicit obstacle; no duplicate dispatch or stale local pin |
| New chat/tree/compact/response repair | Owner origin, generations and original manifest/accounting pins remain truthful |

After correction, run the affected checks, one existing full native gate on the
finished package, installed ordinary Pi transition/reopen proof, and one bounded
read-only evaluator. No real subscription calls are authorized by this plan.
Report failed checks and affected repeats separately from owner acceptance.

Only after package verification: private backup, install, exact repair of the
already leaked ordinary Attempt after confirmed window closure, and before/after
readback of preserved user Work, inputs, results, answers and accounting.
No real Activity recreation, model run or private Git publication is included.
