# One conversational owner — audited implementation plan

## 1. Result, authority and audit

Release candidate: **0.25.0**, branch **codex/single-conversation-owner** from
public main `130fbea98d420b6301a5ec4e16ca152eef8d736f`. The one-owner replacement
and the owner-approved completed-response recovery contract are implemented.
Checked common code is published at `881958e` in public main; private installation
remains a separate pending action.
Actual evidence is recorded in
[the implementation report](single-conversation-owner-0.25.0-result.md).
Core remains **schema 18**: no new tables,
message-delivery obligation or rewrite of old JSON is introduced. A discovered
need to change this architecture stops implementation for owner discussion.

The owner rejected new Core delivery bookkeeping and duplicate suppression.
The owner selected **foreground waiting with progress**, interruption and later
continuation. The ordinary main Pi agent is the sole conversational owner:

    owner -> main Pi agent -> workflow tool -> existing execution
                 ^                  |
                 +---- result / question / obstacle

Workers return addressed facts. Status observers update progress. Neither can
request a conversational turn. Native Pi owns its conversation engine, history
and display. Core/DBOS/WorkPlan retain execution, versions, rights, receipts,
invocation uncertainty and separate owner acceptance.

Confirmed findings and adjacent risks:

- Retained native evidence proves an ordinary final followed by a host wake and
  a second final explaining the same Work result. The extension poller is the
  competing producer; execution workers themselves do not initiate replies.
- Setup/workflow observers also display questions, instructions and raw errors
  separately. These presentation paths require consolidation.
- Current lifecycle tools return after launch and ignore signal/progress inputs.
  Native tools are parallel by default; adding waits needs sequential admission.
- Questions can coexist with independent work and a live RPC. Joining the whole
  executor would withhold a question. Executor exit alone does not prove success.
- Existing empty-final recovery is bound to a host delivery claim. Removing
  wakes alone loses recovery. Reusing that claim for ordinary Work is unsafe:
  opening a new Attempt can change its action digest.
- Startup currently resumes eligible setup automatically. The new foreground
  policy deliberately replaces this with passive discovery and owner-led resume.

Two bounded read-only audits checked producers, concurrency, waits, interruption,
Work/procedure/Sleep and native recovery. A Pi 1.0.4 in-memory API probe passed
three empty/whitespace cases: context omission preserved originals, custom repair
metadata stayed outside model projection and survived compact. No provider HTTP
or disk session was created. This proves API feasibility, not the complete path.
The original trace lacks exact timer reads; reproduce the competing path with
a controlled native provider before attributing its full scheduling sequence.

## 2. Single entry for conversation and foreground execution

- Remove worker-state-driven `sendMessage(triggerTurn=true)` and completion-wake
  creation. No replacement timer, delay, digest cache or natural-language filter.
- Give execution/status helpers narrow typed progress/outcome interfaces instead
  of the full native messaging/UI API. One ordinary presenter owns questions,
  confirmations, readable status and same-run recovery.
- Passive status shows process name, phase and progress. Saved questions, worker
  JSON, instructions, raw errors and identifiers are not separate explanations.
  Detailed diagnostics remain available by explicit addressed inspection.
- Preserve native exact confirmations for acceptance, rights and publication;
  ordinary saves receive no additional confirmation.
- Keep ordinary/assigned launchers' explicit extension allowlist and
  `--no-extensions`. Unsupported custom conversation origins stop before HTTP.
  Old product wake entries remain history and are filtered from provider and
  compaction inputs; they cannot activate old tasks. Arbitrary native extensions
  share messaging privileges and are outside this isolation contract.

Add a shared, non-persisted adapter **ProcessBoundary** view and
**/v1/process-boundary** observation endpoint. Target kind is setup/workflow/
procedure with its exact identifier. Capture target, committed operation/receipt,
native session/branch generation and execution identity before waiting. Mutable
UI selection cannot change the observer's target or cancellation scope.

The view contains subject revision, current action/ref when available, addressed
question/result refs, progress and factual runtime metadata. Boundary kinds:
running, question, result, paused, cancelled, attention, stopped. These are
derived tool facts, never another persisted execution graph/status authority.

- Activity submit/resume/retry, workflow start/answer/resume/retry and procedure
  execution await this boundary in the original native tool. Read/status,
  attachment and routine saves return directly. An answer that preserves an
  explicit pause returns the paused boundary.
- Lifecycle/selection tools use native sequential execution. Parallel model nodes
  remain inside the existing coordinator and keep current resource/model limits.
- Use native progress and abortable observation, with HTTP observation windows
  bounded to 20 seconds. Do not detach to background after a timeout.
- Return exact saved actionable waits promptly, including nested/native RPC
  waits, even while authorized siblings continue. Use Core wait/action views,
  not only `next_action == answer`. Multiple waits remain individually addressed.
- Return setup readiness only after checked activation effects. Missing executor,
  unknown send, resource refusal or failed diagnostic persistence produces a
  concrete obstacle/read error, never infinite waiting or inferred success.
- Wait outside coordinator/bridge locks and SQLite transactions. Do not join an
  RPC waiting for the owner's answer. Recheck current rights and exact versions.
- A lost launch response is resolved through its existing receipt/current public
  state. Never create another operation, Work or send to discover its outcome.

Ordinary Work already runs in the main agent; its publication needs no waiter.
Sleep keeps its existing prepared composite Work/analysis, cursors and change
admission. Procedure execution uses the same foreground boundary contract.

## 3. Questions, interruption and recovery

The main agent uses existing originals and asks only missing owner decisions.
Internal setup/review results become saved facts and diagnostics for that agent.
The agent explains what happened, what is needed and the next useful action.
Address answers to exact saved questions/revisions and consumed owner Sources.
Confusion, history, notifications and repair metadata cannot automatically answer
a question. The model decides meaning; no keyword parser is added.

Native abort promptly cancels observation and requests addressed runtime pause/
Attempt stops through existing Core operations. Separate the stop request from
bounded cleanup joins so abort, manual compact and session replacement can settle.
Preserve results and unknown accounting; neither cancel nor accept domain Work.
An unconfirmed stop stays stopping/unknown. Fence callbacks by captured generation
and execution identity; late results cannot enter a replacement conversation.

Opening Pi only discovers saved continuation and shows concise status. It makes
no model call or automatic executor launch. A new owner request continues through
the main agent; several processes require a short choice by readable names.
Preserve old `auto_resume` bytes and stage protocols without rewriting history.
Authorized siblings may save results after a question ends the conversation;
they cannot begin a new conversation. New background speaking behavior is excluded.

### Empty finals within the same native conversation

Retain exact terminal bytes in Core before classification. Add a **public
read-only terminal-validation API** over existing Source, Context and immutable
invocation correlation. Return the exact tuple and visible/empty/attention/
unknown outcome with stable diagnostics. Check whole refs, current rights,
session/epoch, native entry and actual accounted invocation. Do not depend on
current action digests or add a Core delivery ledger.

For an accounted completed-stop empty/whitespace final only:

1. Pin the exact consumed owner entry/Source root, preserving it through tool
   turns and automatic compact.
2. At native turn_end, return a typed **CustomEntry** naming that root, branch,
   prior invocation/manifest/terminal Source and correction ordinal; also return
   native **context_edit** omitting only the empty assistant entry, and
   `continue: true`. Pi commits drafts before continuation. Originals remain.
3. Derive at most **two reserved corrections** from persisted branch entries,
   not a local counter. A duplicate callback cannot reserve another correction
   for the same invocation. A crash after reservation consumes allowance
   conservatively without inventing a send.
4. Continue the same main conversation with host-controlled **response-only
   admission**. Preserve owner-root provenance and per-request Work/Attempt/
   session correlation. Deny mutations, owner answers, file/command writes and
   acceptance at both tool and bridge gates. The repair request exposes no model
   tools: its checked packet and completed native run already supply the facts.
   Include checked prior proof/current
   facts in the next manifest. Fresh owner input restores ordinary authority.

Do not force one Attempt across the logical reply. Publication and compaction
intentionally close pins; each repair HTTP uses its current admitted pin and
each final proves its actual producing Attempt. Keep publication-time closure,
stale checks and completion proof. Setting host origin merely to suppress writes
must not accidentally drop ordinary invocation correlation.

Tool-use, truncation, error, abort, unknown send, missing proof, storage and rights
failure do not authorize repair. Abort, new owner input and switch/fork/tree fence
old continuation. Reopening never automatically resends an old reply. Exhaustion
shows a concise obstacle with preserved state. Old delivery records remain
readable and their uncertain outcomes are never rewritten as success.

## 4. Tests and acceptance evidence

Extend existing tests/probes for independent risks. Use actual native Pi, raw
provider strings, public Core and disposable fictional spaces. Use controlled
provider barriers instead of timing delays. Check HTTP, manifests, native
entries, receipts, originals and acceptance, not exact wording.

| Scenario | Required evidence |
|---|---|
| Publication during ordinary final | Baseline competing path reproduced; replacement has no completion-triggered run after a visible final |
| Complete Activity setup | Original tool reaches preparation/full review/corrections/activation and returns current result/first action |
| Short/detail/reused input, confusion and two questions | Original Sources/answers exact; no self-answer or cross-process answer |
| Waiting branch plus held sibling/live RPC | Question returned before sibling release; no join; sibling saves without conversation |
| Two lifecycle calls/processes/windows | Sequential mutations, addressed results; no duplicate Work/operation/send |
| Abort/close/switch/fork/tree/manual compact | Prompt cancellation, preserved stops/unknowns, no late result in another branch |
| Empty/whitespace/tools/truncation/HTTP failure | Only known empty finals repair; two reservations survive compact; no effects or unknown-send retry |
| Crash after launch receipt or repair reservation | Exact recovery; no guessed send, duplicate launch or reset allowance |
| Missing executor, diagnostic-write failure, revoked/deleted basis | Concrete obstacle, no hang/false readiness/new model send |
| Reopen ready/waiting Activity and Work | Facts/next action reachable by owner input; no startup model call |
| Procedure, Development and Sleep | Resources, per-request pins, cursors/results and separate acceptance preserved |
| Unsupported custom input, legacy wakes, backup/deletion | No unauthorized conversation; history readable; unavailable repair bases fenced |

Run an installed-wheel full path: creation -> answer -> preparation/review/
correction -> readiness -> first ordinary Work -> compact -> close/reopen ->
continuation. Include parallel waits, interruption, malformed/empty output,
second process and selected project/model/reasoning. Verify actual provider
packets and ContextManifest. Scripted providers prove mechanisms, not universal
model interpretation.

## 5. Delivery and defaults

1. Reproduce the current bug and verify native foreground question return, abort
   and same-run repair early. Failed native feasibility stops delivery; no
   upstream runtime patch, alternate engine or temporary fallback.
2. Implement one-owner ports, addressed observation and foreground tools, then
   response-only recovery and passive startup/UI. Run affected checks.
3. Run one full native gate on the coherent package; repeat affected checks after
   corrections. Check the final wheel outside checkout and one bounded read-only
   evaluator smoke. Preserve meaningful old assertions while replacing obsolete
   completion-wake expectations; never skip/delete tests to pass.
4. Report exact source/wheel SHA, actual outcomes, failures and evidence limits
   separately from owner acceptance. Publish checked code to
   `ainazemtsau/zaratustra/main` and verify by authenticated readback.

No personal Activity deletion or ZT update belongs to this package; those remain
separate owner actions. Exports/Git projections, new services/queues and domain
templates are excluded. Preserve unrelated dirty work and old canonical bytes.

No fresh real-provider allowance exists. Make no automatic real-model trial;
future trials require separate bounded authorization. The audit made zero
provider sends and is not a claim that implementation/end-to-end checks passed.

**Readiness:** ordinary Pi has one conversational owner; execution returns through
its original tool; questions, interruptions, reopening and known-empty recovery
preserve exact history without independent completion conversations, repeated
effects or hidden acceptance.

Next: solmax.
