# Stage 3 — web discussions and recoverable incoming requests

Owner approval: «ок» on September 17, 2026, after the shown ChatGPT → GitHub → Pi
scope. Baseline a3e1c970bee97ef73c49084c1b940665d4bed4db, candidate 0.21.0.
This is one new capability over stages 1/2A/2B. No Direction task is formally closed
by implementation evidence, and no personal installation is automatically updated.

## User path

Ask Pi to prepare selected material for a discussion. It saves a dated packet of
chosen exact sources. On a publication instruction it publishes that packet and
the generated Project instructions to the chosen GitHub repository. The owner
uses those instructions in a ChatGPT Project and discusses the question. On a save
instruction ChatGPT creates a new free-form request file. Later the owner asks Pi
to process incoming requests; Pi captures originals, interprets all items, performs
authorized effects and asks for missing named files. A fresh chat reads unfinished
progress or verified completed results from the same Process.

## Implementation boundary

Installed CommandSpec registration shares names between Pydantic command validation,
generated host schema, dispatch and the skills capability catalog. command.list
progressively supplies the payload schema for a selected extension. Built-in
operations retain their input and behavior; data never imports executable handlers.

web_channel, web_request and web_context are managed registered journal types.
They use existing Core schema10 immutable materials, mutation receipts and journal
revisions. No new database, mandatory Work, Pack or legacy workflow is introduced.
Generic record writes cannot bypass their dedicated commands. Source reads/history,
search and exports use the existing public mechanisms and pinned references.

web.configure stores a selected repository/branch in one Process. web.prepare saves
only the question and exact selected sources. It does not follow links or copy
binary attachments, history or the Home database. web.publish writes the selected
packet and instructions as immutable files under that Process's transport prefix.
It refuses differing remote content and replays identical publication safely.

GitHub uses the existing authenticated gh CLI. Remote reads resolve one commit/tree
and verify blob bytes. Writes use the GitHub contents API create operation without
replacement SHA; concurrent creation cannot silently overwrite an existing file.
No checkout merge, git reset, background polling, remote database synchronization,
new account, service or access grant is involved.

web.pull captures a bounded page. Exact original UTF-8 and origin/blob/hash are saved
in one journal revision. Broken JSON/YAML is ordinary text; no source schema is
required. Repository/path/blob determine retry identity, independent of an agent's
operation id. A changed source becomes new input; original revisions remain.
Remote files remain immutable, while completed local tracking excludes replay.
Failures are per-file and pagination explicit. Empty, non-UTF8 or >1 MB request
files produce visible failures; substantial binary/report data travels as attachments.

web.review records agent-authored interpretation and per-item progress. Literal
source and authority quotes must occur in the original. Actual meaning, authorship,
completeness and the live owner's permission remain the agent's responsibility.
Code validates type/scope/reference existence and actual document attachment sources.
web.attach reads an owner-supplied file directly and preserves its exact bytes in
a pinned document revision (existing 8 MB limit). It binds that revision to the
declared attachment. Retries recover interrupted binding without another copy;
later document edits cannot substitute different bytes. web.review cannot fabricate,
clear or replace a received attachment reference. A corrected file is a separate item.
It refuses dropped known items and rewriting completed effects. Deterministic
delivery ids and committed journal results support recovery after an interrupted
progress update. A multi-step decision retains separate per-step operation ids.

web.complete requires every declared item delivered, required files supplied and a
fresh request/Process revision. It never guesses missing content, adopts a report's
recommendations or switches focus. Context references reveal changed selected record
versions; the agent reviews other changes and actual semantic conflicts. There is
no automatic merge or claim that unchanged selected versions imply global freshness.

## Integration and limits

The normal Pi and Codex connection exports include the shipped intake instruction.
An existing installation needs the new package and explicit managed connection
update. The owner uses ordinary requests, not internal schemas. Separate ChatGPT
Projects can target different Process inboxes in one Home and one personal repo.
The prepared text is readable/copyable without a provider-specific manual adapter.

GitHub authentication on the local host does not prove ChatGPT can create files.
The real account-specific ChatGPT write route and personal hookup need their own
visible first transfer. Project instructions do not add absent capabilities.
Attachments are supplied by the owner; generated files and private chat URLs are
not assumed remotely downloadable. No model routing, subscription purchase,
automatic ChatGPT launch, provider API run, Stage4 or full migration is included.

END_OF_FILE: docs/stage3/IMPLEMENTATION.md
