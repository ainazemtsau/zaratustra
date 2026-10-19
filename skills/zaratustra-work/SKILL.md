---
name: zaratustra-work
description: Create and continue durable activities, goals and concrete input waits with Zaratustra's first-block tools.
---

Inspect zara_map and bounded activities/work cards; read candidate records.
Interpret the user's goal yourself. Core is persistence, not a planner or translator.
Reuse an existing Activity when appropriate; ambiguous similar goals need clarification,
not silent deduplication. A short thanks needs no Work.

For a connected save, allocate one request_id for this intended transaction. Get the exact
observed source handle from the current snapshot. In zara_commit include source_handles,
reason, guards and ops. import_evidence takes client_ref, source_handle, English title and
source_language; it preserves the original text automatically. create_record takes client_ref,
kind, title, optional body, visibility:"workspace" and typed data. Link new objects with
{client_ref:"name"}; permanent refs are {id:"..."}, optionally with revision.

Activity data: purpose, status (active/paused/closed).
Work data: activity_id (ref or null), parent_work_id:null, objective,
acceptance:[{criterion_id,description,verification,required}], status,
current_state,next_action (English string or explained null), steps:[],
waits:[{wait_id,kind:"user",target:"work",subject,satisfied_by,received_refs:[],question}],
context_refs:[evidence refs],completion:null.
Missing expected material means waiting with a meaningful question; blocked means intervention
is needed. Active Work requires a next action. No terminal completion or nested plans are
implemented yet. A newly received excerpt need not satisfy a whole-book wait.

Save language preference as knowledge: knowledge_kind:"preference", statement,
state:"current", basis:"user_statement", evidence_refs, conditions (English string),
representation:{kind:"English paraphrase",source_ref,source_language}.
An optional set_focus op has activity_ref and work_ref; focus is session convenience.

Report saved state only after committed:true. Explain continuation in the conversation
language. A new process discovers actual Work through catalog and reads it; never ask the
person to reconstruct the plan or enter identifiers. Corrections use update_record with
the complete typed data and guards:[{ref:{id},expected_revision}]. Old revisions remain.
