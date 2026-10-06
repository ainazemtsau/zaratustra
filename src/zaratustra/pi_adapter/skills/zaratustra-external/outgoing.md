# Prepare context for an external discussion

This is the optional one-time discussion path, not a mandatory goal-selection wizard
and not a replacement for regular service setup. Prepare only the context needed for
the owner's stated question and chosen destination.
Read the selected Activity, relevant Work (if any), supplied sources and saved service setup.
Do not export all memory, other Activities or an entire checkout by default.

1. Identify what the owner wants to discuss and what the recipient actually needs to
   answer. Distinguish the shared product/repository from the owner's local installation.
   Do not include credentials, unrelated personal data or private paths just because they
   are available locally. A public repository URL does not make instance data public.
2. Explain the content and destination of the proposed handoff. Manual preparation does
   not transmit anything; do not invoke a paid API or automatic upload.
3. Prefer one self-contained text document for the first route. Include the actual question,
   relevant Activity goal, known constraints, selected context, exact source/version basis,
   open questions and requested return. Mark missing repository access and unknown facts.
   If the recipient can read a relevant public URL, it can be included with a fallback for
   inaccessible content. A file package is optional, only when requested and actually useful.
4. Save the actual complete document through `zara_integration`, adapter `manual`,
   operation `prepare_document`, after reading its contract. Supply the chosen Activity,
   optional Work and selected exact `context` references. Core adds scope anchors and
   retains a prepared Handoff; this does not send it. Read it back completely through
   `read_document`. Save a scoped Claim pointing to the Handoff so it can be found under
   this Activity and service after restart. Raw `zara_memory` Handoffs remain supported
   for more specialised cases, with a genuinely observed state revision for their basis.
5. Provide a copyable block. If the owner asks for uploadable files, use an explicitly
   chosen export directory in the allowed working resource, not the installed package or
   the product's documentation directory. Confirm which files belong in that handoff.
   Keep Core references and export coverage clear; do not claim a multi-file exporter is
   implemented or tested merely because an agent can write a file. Never overwrite an
   unrelated file. Do not package a whole repository as an implicit fallback.
6. Keep `prepared` until a separate report or receipt establishes transmission. The owner
   copying or uploading a file is a manual transfer. Record their report as a new Source
   before advancing to `reported_sent`; direct delivery requires its own evidence.
7. A returned answer is a separate Source through intake.md. Preserve differences between
   the issued question and the received answer. Association is not acceptance of its claims.

A changed document is a new handoff, not a rewrite of an old handoff's text. Revise the
scoped setup/preparation Claim to point to the new exact address and retain history.
Future automatic transports must compose these same Core authorities and evidence stages;
this workflow does not implement or silently enable them.
