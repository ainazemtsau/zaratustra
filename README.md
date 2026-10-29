# Zaratustra

Persistent Activity, work, selected memory and bounded improvement reviews for Pi.
The owner works through chat; agents use typed operations and exact sources.

The file-primary generation requires **Pi 1.4.0 and Node 24.22.1** on Windows x64.
It preserves the existing product rather than introducing a second planner, server,
launcher or model. Parallel qualification is limited to ten local processes.

## Where data lives

- `memory/corpus.json` identifies the portable corpus, its format and committed revision.
- `memory/objects/` contains small versioned typed entries and retained legacy information.
- The corpus includes the hashed parts needed to restore selected originals and versions.
- `activities/` contains optional working Markdown documents at their existing paths.
- `.local/memory/` contains the rebuildable SQLite projection, local coordination and caches.

Canonical files are durable truth. A SQLite file alone is not the memory backup.
The projection can be rebuilt from a verified corpus without its old SQLite database.
Externally editing canonical envelopes is unsupported; drift is an error to inspect,
not permission to overwrite. Ordinary managed documents remain editable through Pi.

The semantic names map onto compatible existing types: Note → Knowledge,
Episode → meaningful Run, Procedure → Method, Source → retained Evidence,
Document → managed-document Entity. Existing IDs, exact revisions and links survive.
No separate schema or SQL table is created for each Activity.

Each Activity has a short contract: purpose, boundaries, current context, open work,
documents and applicable procedures. It grows subject-specific documents only when
needed. Structured content and exact versions can support other readers without
requiring ChatGPT Web to understand SQLite. The agent maintains this structure.

## Ordinary use

Install the exact published commit, accept native Pi project trust, and run Pi in
the project root. Existing schema-9 workspaces require the explicit safe migration;
installing new code must not silently migrate a live personal database.

```powershell
pi install --local git:github.com/ainazemtsau/zaratustra@<exact-public-commit>
pi
```

Ask to continue an Activity, save a useful constraint, correct an interpretation,
prepare a document, or read its exact source. Conversation and originals keep the
user's language; canonical working formulations remain English.

Successful reads and ordinary tool calls do not automatically create permanent
Evidence. A durable source has a purpose: continuation, obligation, constraint,
important decision, reusable experience or an explicitly selected original.
Short exact fragments may be retained instead of full output; omitted text is never
presented as available merely because its hash is retained.

Explicit temporary candidates/selected diagnostics last at most seven days within
20 MiB. Necessary grounds of open obligations and UNKNOWN effects are protected.
Migration preserves previous durable data losslessly; it does not model-delete it.
Legacy history stays explicitly addressable and is excluded from ordinary discovery.

## Sleep

Ask for a review or use `/zara-sleep start`. `zara_sleep` also supports `resume`,
`status` and `cancel`. One review is active per workspace; ordinary agents continue.
It selects at most ten meaningful cases, permits at most three improvements, and
admits at most twenty logical model generations within fifteen minutes. The first
limit wins; restart does not reset the budget.

The controller enforces reading, analysis, proposal, validation, application,
future check and registered completion. Its isolated in-memory SDK session uses
the selected model, thinking level and Pi authentication, without unrelated
extensions, shell, recursive Sleep, warming, compaction or automatic retries.
A limit refusal happens before the native stream delegate. Logical generations
are different from transport-level HTTP/WebSocket exchanges.

Reversible duplicate corrections, bounded organization and explicitly local
procedure/document changes may be delegated. Goals, important commitments,
permissions, identity merges and irreversible removal need appropriate authority.
Observation, hypothesis, applied change and later demonstrated usefulness remain
separate. A future observation can support or refute a recorded benefit check.

## Private Git checkpoint

Trusted setup binds one private repository and `main`; tool arguments cannot change
that destination. `zara_sync` reports status or retries pending delivery. With a
binding, changes across the working repository are coalesced after two seconds;
startup, agent completion and orderly shutdown also request a checkpoint.

The checkpoint includes canonical memory, documents, selected sources and other
working files. Dependencies, derived databases, OS leases and temporary caches are
excluded precisely. Existing staging, unresolved Git operations, branch changes,
remote divergence or oversized outgoing blobs stop automatic publication with a
reason. Staging is not reset; there is no force push or automatic rebase. Active hooks, signing
and external clean/process filters defer to a manual checkpoint; owner checks are not bypassed.

`LOCAL_SAVED`, `LOCAL_COMMITTED` and `REMOTE_CONFIRMED` mean different things.
An offline push leaves local data safe and retries the existing commit. Only a
verified remote commit covering the actual checkpoint confirms GitHub delivery;
late callbacks cannot confirm a newer epoch or unsaved subsequent edits.

See [file-primary design and upgrade](docs/MEMORY-V2.md). Public publication and a
personal installation are separate. A personal update needs closed old sessions,
a verified full cold copy, quarantine migration and an independent corpus rebuild.

## Development and limits

Use `npm ci`, `npm run types`, `npm run lint`, `npm run boundary`, `npm run build`
and the focused suites declared for the change. Synthetic test workspaces must
stay outside real ZT/Health. No personal sources or credentials belong in this
public repository. Historical qualification reports remain evidence of their
specified versions, not automatic acceptance of this one.

This release does not add Codex integration, a standalone server, weight training,
concurrent multi-computer merge or proof of usefulness over years. Local scopes
are managed API permissions within a trusted personal process, not OS isolation.
