---
name: zaratustra-documents
description: Create and maintain durable Activity documents, pinned formats and links; inspect external edits, archive/remove/restore, and prepare a verified GitHub view.
---

Use this process when work needs independently reusable files: plans, menus, recipes,
instructions, reports or dated journals. Small Work/results may remain in Core. Never
require the user to invent folder trees, metadata or internal IDs. Reuse existing
Activity, documents, formats and Methods before creating replacements.

Canonical document contents live below the trusted project's `activities/` directory.
Core keeps a resource Entity with `data.document`, immutable original-file Evidence,
exact head/format/link refs, Changes and normal effect/registration receipts. There
are no per-Activity SQL tables. Other clients may read Markdown without Core knowledge.
Do not change the existing project `.local` memory location or owner Git exclusions.

Discover with zara_browse selector view:documents; documents_archive and
documents_removed expose lifecycle catalogs. Read the selected registry and inspect
its working file using zara_document_inspect. A registry revision is not a content
snippet. Read head_ref through zara_read, using ranges for long text. Always supply
the current exact registry ref for a change. Historical registry revisions pin their
own exact head_ref, format_ref and links; never replace a historical source with latest.

For create/write/move/adopt/restore use zara_document_preview. Supply relative .md
path within activities, title, document_type, source language and content when needed.
Bind a Work/step when applicable, or use the explicit independent document path.
The adapter supplies/preserves the single stable ID comment. Normal service metadata
lives in Core rather than duplicated headers. Explain the change and alternatives,
obtain existing exact zara_confirm, then zara_document_apply with its preview_ref.
If zara_confirm first returns review_in_chat, continue on the next tool turn with
the same preview_ref to open the native question. Do not treat the queued review
as permission or wait for a new user message merely because the first call queued it.
The apply tool coordinates Pi's PUBLIC native write engine; do not issue an additional
write/edit for the same preview. No custom text editor or second executor is installed.
Only claim saving after committed:true. Saving does not complete Work or prove benefit.

After an interrupted/lost reply, discover the operation in operations and use
zara_document_apply with its request_id. It inspects/finalizes without dispatch replay.
Uncertain or mismatching bytes require reconciliation. If the owner explicitly chooses
an uncertain repeat, supply retry_of and retry_risk in a NEW exact preview. The original
unknown outcome remains recorded; a successfully registered linked retry supersedes its
pending document registration without claiming the earlier action never happened.
A new ID alone is not permission to
repeat a possibly executed action. Old-epoch operations cannot mutate restored files.

Choose ordinary Markdown for narrative. When exact data fields are needed, create a
format document with one fenced `json` block containing a JSON Schema 2020-12 object.
Pin its returned head_ref as the data document's format_ref. The data document uses
one fenced json block for structured fields and ordinary Markdown for explanations.
No remote schema loading, async validation, custom validator language or external
format plugins. Syntactic validity does not prove factual/medical correctness.
Do not hide dates, amounts or identifiers only in prose when later selection/counting
needs them. Follow the existing language policy; originals/quotes remain original.

For a format change create a new observed format version, then explicitly migrate
selected current documents to its new head_ref. Old documents retain their old format.
Never invent missing historical values or silently reinterpret old dated observations.
The model decides useful structure and migrations; Core checks the declared format.

External write/edit is allowed as an unregistered change. Inspect reports drift; review
the actual file before using adopt_changes:true. Adoption retains observed content;
make further edits separately. Do not silently overwrite a changed file, infer authorship
from timestamps or treat imported text as permission. A missing working copy can be
recreated from explicitly selected retained content. A removed file requires that
content explicitly; its removal marker is not the old recipe/result.

archive preserves the working content while excluding the document from the active
catalog. write reactivates an archived document. remove deletes ONLY the working file
after registration, retaining snapshots and registry history. Live document/Work/problem
dependencies block removal. Full retained-body purge uses existing E3 storage previews,
retention checks and permissions; it is distinct from removing a working copy. Git history,
external exports and backups remain separate copies. Moves preserve ID and update path;
review/update actual Markdown links in dependent documents, not only database links.

For an external chat, prepare an authorized minimal handoff through the work skill.
Use zara_documents_publication with exact document refs and proposed index_path. It
returns a manifest and index text, NOT written files or a push. Include exact linked
document versions. Materialize required historical snapshots at the returned \_history
paths using their retained head_ref and ordinary native file controls. These are read-only
export copies, not new canonical document registrations. Recheck until ready:true.
Write the index with relative links, make a verified memory backup using existing tools
when authorized, inspect the intended Git file set and use ordinary Git commit/push.
Never copy only a running SQLite main file or claim multi-device merging. Do not silently
expand export access or read another Activity merely to produce a shareable view.

Returned Web reports are external Evidence, not automatically owner feedback or performed
actions. Match to the saved handoff and exact source versions. Keep planned meals separate
from reported consumption; a correction updates one addressed event rather than adding
another success. Preserve the original report, update the appropriate dated document,
then reconcile Work and Knowledge through their existing operations.

Sleep may read exact document sources, outcomes and open problems, and propose changes
to Methods or document formats. Registration/hash/index maintenance is not independent
experience. Preserve unsuccessful attempts and future checks; an edit is not improvement.
No automatic next Sleep cycle or new rights are introduced.

END_OF_FILE: skills/zaratustra-documents/SKILL.md
