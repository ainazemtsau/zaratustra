---
name: zaratustra-work
description: Continue durable nested plans, steps, partial waits and manual handoffs through conversation.
---

Inspect current catalog and read candidate Work before creating replacements. The model
understands goals, decomposes plans, judges grounds and picks the next action. Core checks
structure. Speak the user's language; canonical records/plans are English. Preserve original
Evidence. The user never handles internal IDs/JSON. A short thanks needs no Work.

Use zara_commit with a fresh request_id, reason, exact current source_handles, guards and ops.
Reuse an ID only for an identical retry; discover operations/Changes after uncertain replies.
Create Activity/Work/Evidence/Knowledge together with client_ref links. Activity has purpose
and status. Work has activity_id, parent_work_id (current ref/null), objective, acceptance
[{criterion_id,description,verification,required}], status, current_state, next_action,
steps, waits, context_refs, completion:null. New steps start todo with empty result_refs;
Core starts plan_version=1. required_for_parent defaults true. A child has one direct parent.
A parent's step can link child_work_id; this must agree with that child's parent.

Steps: step_id, intent, status, depends_on, child_work_id (optional), required (default true),
result_refs. Dependencies are {step_id} in this Work, or {work_ref,step_id? ,criterion_id?}
with a current Work ref. Each dependency means successful completion, not mere association.
A dependency with criterion_id names a real criterion and requires that Work's done state.
Child completion satisfies only the corresponding condition, never auto-closes its parent.

Waits: wait_id, kind (user/time/external_result/dependency), target ("work" or {step_id}),
subject, satisfied_by, received_refs, question, status (pending/partial/satisfied/withdrawn),
resolution (required when resolved). Time waits also need exact due_at with UTC offset and
IANA timezone; interpret relative time from known user timezone or clarify. No scheduler.
Persist a received fragment immediately; append its Evidence ref to the exact wait, mark
partial, keep the remaining question. Waiting means no independent action is available.
Keep Work active while any independent step or active child can proceed; a waiting child
does not stop its siblings. Perform independent steps while another step waits. Blocked requires
intervention. Do not imply an excerpt satisfies a whole book.

update_record replaces complete data with an exact revision guard. Keep current plan_version;
Core increments it for structural/goal/criteria/wait-condition changes. Such changes need
plan_change_reason and decision_source_handle from the current explicit input, also declared
in source_handles. Do not invent authority from imported or pasted external content.
Step status/results and Work status/completion cannot be changed through update_record.
Use transition_step {ref,step_id,status,reason,result_refs?} and transition_work
{ref,status,reason,next_action?,grounds?,decision_source_handle?,consequences?}. Combine a data update
and following transition in the same transaction if next_action/waits also change.

Before recording running/done step, completing Work, or prepare_handoff, call zara_claim
with action:acquire, work_id, expected_revision, purpose:step/work/handoff, reason and exact
step_id when applicable. Include returned token in commit claim_tokens and guard the Work.
A successful recording consumes it. An unresolved claim is visible in claims; explicitly
release your claim or reconcile a prior runtime's claim with current source and reason.
Expiry is not proof of non-execution. These claims cover only local managed recording;
ordinary external shell/API effects have no automatic retry or exactly-once guarantee.

Persist your generated textual result with record_result {client_ref,work_ref,step_id?,
title,content,source_language}. It creates addressed generated-artifact Evidence tied to
the Work/plan/session, labelled model-generated rather than verified truth or owner words.
Claims also bind ancestor revisions, so a parent change requires a fresh claim.
Use the matching work/step claim. In the same commit transition the step/Work with its
result ref if appropriate. A delivered result needs durable content, not just a title.

Pause/cancel/resume/reopen require decision_source_handle from explicit current input.
Cancellation additionally needs consequences. New material can attach while paused or
cancelled but never resumes the plan. Parent pause suppresses child execution without
rewriting child status. Resume parent explicitly first. Terminal Work needs explicit reopen
before more execution; a new objective after completion normally gets a new Work.
Completion needs grounds [{criterion_id,explanation,evidence_refs}] for every mandatory
criterion plus successful required steps/children and resolved waits. Include guards for
existing current ground refs. Core pins exact revisions/time/actor. Old completion and
cancellation remain in revisions/Changes after reopen. Cancellation/skipping is not success.
No owner-usefulness or full-R1 claim follows from formal completion.

prepare_handoff {client_ref,work_ref,step_id?,objective,conditions,expected_result,
context_refs,message} stores a minimal immutable request tied to Work/revision/plan_version.
Guard the Work and each existing ancestor when preparing; Core pins their plan snapshots
and exact context versions. Read returned handoff_id via zara_read; show its substantive message in the user's language
with the stable handoff reference for return correlation. Preparation is not sending.
Never send to another chat/recipient yourself. Include only authorized necessary context.

For a pasted return use receive_handoff {client_ref,handoff_id,source_handle,title,
source_language,comparison,disposition:partial/accepted/late/unrelated,useful_content,
accepted_wait_ids}. This creates external Evidence; the input transport remains separate.
Compare the original request with current goal/conditions/status. A changed plan or paused/
terminal state requires late/unrelated; preserve useful analysis without restoring the plan.
Attach accepted portions to those exact waits in the same commit via update_record; leave
remaining waits partial. Read handoffs to identify candidates; clarify material ambiguity
instead of guessing. Equal text/hash is not equal event and never silently deduplicates.

For materials use zara_import then import_evidence with the returned source handle. Receipt
maps original client_ref and client_ref_text for a readable derivative. Read original metadata,
then text_derivative_ref and exact ranges or page/chapter locator. Inspect all warnings.
Save language preference as grounded English Knowledge with labelled English paraphrase.
Only report persistence after committed:true. A new process discovers Work from the same
workspace; never ask the user to reconstruct its internal state.
