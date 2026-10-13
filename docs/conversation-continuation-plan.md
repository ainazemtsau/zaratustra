# Conversation continuation: implementation and audit plan

## Authority and scope

The owner authorized the common correction, audits, tests and ordinary installed
Pi verification, followed by selected personal cleanup for a fresh owner trial.
Candidate version: 0.24.0. Explicit Core upgrade: 16 to 17. Existing immutable
payloads/checksums and separate Work acceptance remain. The current personal
Activity remains intact during implementation. Export and Git projections are
outside this package. No real-provider trial is authorized by this plan.

## Confirmed gaps

1. Setup ready is rendered as instructions and Work identifiers in a widget;
   the conversational agent does not receive the completed state.
2. Completed setup is excluded from pending startup recovery.
3. Native Pi custom messages become provider user messages. They cannot carry
   trusted control or acquire user-answer authority.
4. Native custom wake bypasses ordinary input/before_agent_start preparation.
5. Bridge last_sources records latest receipt, not necessarily the input consumed
   by the active model/tool chain; queued input can replace it.
6. Calling native sendMessage does not prove delivery. Native queues are volatile;
   toolUse/message_end does not prove a final saved conversational answer.
7. Initial Work selection is command-only. Ordinary assistant continuation needs
   an addressed selection route; it must not accept or duplicate the Work.

## Core contract

Add a narrow conversations module and additive schema 17 with typed delivery
metadata. The Work/Workflow/Setup/Procedure state remains the authority. Actions
are derived current views, not a second execution graph or editable status.

`ConversationActionView`: stable id and digest; subject kind/id/revision;
Activity/Work; action kind (question, ready, result, attention, paused, cancelled,
available_work, running); exact sources/result refs; question/purpose/answer target when
present; readable name and next action. Discovery is bounded and rights checked.
Suppress internal setup/workflow children in ordinary discovery. Include completed
setup and ordinary proposed first Work, even after notification was delivered.

`ConversationDeliveryRequest`: host claim, context inclusion, final response,
unknown or abandonment. Store action id/digest, actor/epoch, host and native
session/branch, manifest/invocation refs and captured assistant Source/entry.
All changes use normal Core operations/audit/receipts. A global action claim avoids
two windows issuing the same automatic followup. Observe actual provider requests
through existing knowledge_delivery; UI delivery is not invocation accounting.
An answered provider tool call is not a completed conversational delivery.
An unknown send is never blindly retried. Unsented abandoned claims can be released
after session fencing; after send, recovery requires exact observed evidence.

Derivation changes invalidate prior action digests. Recheck rights, current epoch,
subject and all bases before HTTP and before effects. Old action history is not
fresh authorization. Include new edges in backup, restore, deletion and sanitation.
Never weaken strict deletion-address checks introduced in 0.23.5.

## Conversation origin and native delivery

Fence the native role-user ingress: extension-origin input is retained as a
non-owner technical receipt and handled before it enters the native user branch.
Extensions must use the Core host continuation route. Capture newly delivered
interactive/owner-RPC native entries by session and entry id from the persisted
branch. Preserve raw receipt originals separately without guessing associations
by text, markers or FIFO. Startup history is not fresh owner input. A model can
choose an exact answer Source from several delivered owner entries; opening a
new question does not let an earlier goal silently become its answer.

Use native Pi followUp scheduling for an asynchronous result. Its hidden custom
entry carries only a checked action address and session generation. Filter the
token before custom-to-user conversion and from both compaction inputs. Include
the checked action packet through context_with_system and the actual ContextManifest.

Bind every provider/tool chain to an immutable origin: actual delivered owner
Sources/entry ids, or a trusted host action. Host-only, restored and other-extension
origins cannot answer for the owner. Original receipt and actual delivery are
distinct; do not infer origin from latest text or one global FIFO. Native delivered
entry association must be verified with queued steer/followUp and repeated inputs.
Preserve unsupported input and fail closed rather than select an old owner answer.

Shared preflight covers workspace/resource, model/profile/reasoning, admitted
tools, current context and request origin for both ordinary and host turns. Pin
invocation Work/Attempt context; later selection cannot change the finish target.

Correlate actual invocation, manifest, assistant Source and native turn_end entry.
Only a saved successful final response acknowledges delivery. Actual event facts
remain Core context; model phrasing is normal assistant text. Display a compact
status instead of printing all internal instructions. No health-specific parser
or wording template is introduced.

Retain exact final proof for every successful ordinary final, not only a host
notice. If a window dies after that proof but before stopping its unassigned
Attempt, a fresh host may use the existing stop operation only after Core
rechecks the matching final Source, manifest, invocation, original session,
current rights/epoch and absence of unknown sends or waits. Missing proof never
becomes success. Restore free conversation with an addressed obstacle instead
of blocking the user's request to explain what happened. The native test harness
must wait for durable settlement rather than kill Pi at the earlier agent_end.

## Recovery and first use

On entry and every actual owner request, expose bounded current process/available
result/first-Work summaries. A lost notification does not lose continuation.
An already delivered notice does not prevent answering a new "what next?" request.
At several suitable processes, model asks a short choice using readable names.
Tie automatic wake to the initiating conversation and active native branch;
switch/fork/shutdown fence old callbacks. Other conversation work remains usable.

Provide a model-readable conversation catalog/read/Work selection surface. Selecting
the existing first Work checks origin and exact action/Work state, uses its registered
resource and leaves acceptance separate. Never create a second first Work merely
to get a conversation going. Questions/answers use exact existing wait targets.
Confusion or status requests remain ordinary messages; model decides meaning.

## Implementation order

1. Native feasibility/regressions: custom filtering + exact manifest, delivered
   owner origin versus queued receipt, final turn evidence and session fencing.
2. Typed schema 17/read/actions/delivery operations and data maintenance; old
   canonical/upgrade/backup proof.
3. Bridge origin/context/selection/host endpoints and shared Pi continuation.
4. Route setup, ordinary workflow, procedure and Work through this contract.
5. Installed native probes and adversarial review; one complete native gate.
   Repeat affected checks after corrections. Bounded read-only evaluator smoke.
6. Build checked wheel, report SHA and real evidence/limits. Checked selected
   backup/update/explicit migration, then delete the owner-selected test Activity and dependent Work
   through Core. Preserve Development, independent material and old send accounting.
   Remove exact selected originals used by its setup, including initial
   owner messages retained before Activity scope existed. Check shared dependencies
   in a restored rehearsal; never classify unrelated sources by their prose.
   Prior answer copies are only for this Codex chat to draft actual owner messages.
   Never attach archive/research/old setup to the new Activity automatically.

## Required observable checks

| Case | Evidence |
|---|---|
| Ready while idle or streaming | One logical followup, normal assistant final message |
| Native host token | Absent from provider user messages and compaction; checked system manifest |
| Queued/extension/restored inputs | Exact consumed origin; no old or synthetic owner answer |
| Tool call before final reply | Invocation answered, delivery incomplete until saved final text |
| Lost event/new session/what next | Same Core result and next step; no duplicate Work |
| Abrupt close after saved final/before settle | Exact proof closes only the old ordinary Attempt; missing/unknown proof remains an obstacle and does not block explanation |
| Two processes/two windows | Addressed selection and one automatic delivery claim |
| Changed bases/rights/cancel/delete | Stale action refused before HTTP; independent work preserved |
| Provider error/unknown/close windows | True observed outcome, no guessed success/blind resend |
| Model/resource selection during send | Correct pinned request and finish target |
| First Work/ordinary save | Actual selected resource, retained result, acceptance separate |
| Upgrade16/backup/restore/deletion | Old hashes and data preserved; all new links serviced |

Use ordinary installed Pi with localhost provider and fictional spaces. Inspect
actual HTTP bodies, manifests, saved Sources, receipts and native branch entries.
Synthetic replies establish mechanisms, not universal interpretation quality.
Real subscription trials require a separate explicit send allowance; previous
trial limits are not reset by this correction. Owner recreation is a separate test.
