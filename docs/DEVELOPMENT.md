# Approved first block

The owner accepted specification 1.1 and the concrete first-block proposal with
“принимаю”, then explicitly authorized this executor assignment. This is PROBA:
plan approval is neither acceptance of the future result nor completion of R1.
The only publication route is `ainazemtsau/zaratustra:codex/zaratustra-v1`, starting
from the freshly verified empty `main` at `d956c6dfe18b49754fabd0773b798a01e5fcb017`.
No old checkout/worktree is a source of implementation or disposable data.

The target remains the complete self-contained [specification](specification-v1.1.html).
Original supplied HTML SHA256:
`7d3bd88d71dd954949ad33caae38859f9e06c460b8537ed3259780d11668fac4`.
The original was verified and left unchanged. This public derivative changes only
the personal original-1.0 location to `[owner-local original]/...` in §27.1.
Derivative SHA256: `4940e16e39174df941da98889c43b713c48287d4aeda8754fd57660d462a77cb`.
Normative meaning is unchanged. The document's historical pending-authorization
statements describe its creation; this assignment supplies the later authority.

Settled decisions: Windows 11 x64 first, trusted personal local Pi with one writer,
Git-pinned public development install, English canonical work and multilingual
conversation, TXT/Markdown in this block. Full R1 also requires text PDF and
unencrypted EPUB. Codex is next; Sleep remains R2. The selected Pi provider may
process supplied/ordinary permitted context; other destinations need authority.

## Preserving engineering choices

Node 22.19.0, Pi 1.3.0, TypeScript and node:sqlite are used as suggested. SQLite is
behind StoragePort. Core imports no Pi types and has no model loop. Runtime schemas
are Zod 4.1.12 (MIT); Pi's host TypeBox 1.3.27 describes tools. Host Pi/TypeBox peers
are `*` per Pi package mapping, with tested versions pinned in devDependencies.
No postinstall build or generated runtime resource is required.

§14.2 preserving clarification: in Pi 1.3.0 declarations, `event.prompt` is user
input. The adapter mutates `event.systemPromptOptions.sections.zaratustra` for a
static bootstrap. It preserves all other sections/options. The supported string
alternative would append to `event.systemPrompt`, never to `event.prompt`.
Personal state exists only in one owned custom `context` message refreshed before
each request. No repeated permanent snapshot entries are appended. `details` marks
ownership/runtime; every model-relevant value is in `content`.

## Why each mechanism exists

| Mechanism                                  | Missing property / why reuse alone is insufficient                                                                                          | Authority and removal                                                                       |
| ------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| Core record schemas and ref validation     | SQLite/JSON and Pi history cannot validate linked Activity/Work/Evidence/Knowledge; Zod supplies schema machinery, domain checks stay small | Only low-risk first-block ops; remove adapter to stop access, preserve home                 |
| StoragePort + node:sqlite                  | Disk atomicity, WAL, current records, revisions, Changes and committed receipts cannot be guaranteed by model prose                         | Trusted absolute home; built-in Node SQLite; close DB on shutdown                           |
| Prepared intent and canonical request hash | A dropped response needs discoverable structural identity without fuzzy deduplication                                                       | Same store, no service; receipt replay checks current access; no arbitrary effect guarantee |
| Exact source handles                       | Pi user-role alone cannot certify human authorship or bind an old source to exact bytes                                                     | Runtime-local capabilities; stable observed refs in payload identity; expire on shutdown    |
| Immutable file staging/readback            | SQL transactions do not retain material bytes atomically                                                                                    | Permitted roots, UTF-8, 1 MiB; orphan blobs may remain, no automatic cleanup yet            |
| Single-process writer lease                | SQLite locks serialize transactions but not agent execution across thinking time                                                            | Personal deployment, second process read-only; dead PID reclaim; no OS isolation            |
| Request-local snapshot                     | Pi history/tool results can be stale after a correction                                                                                     | Own custom message only; replace per request; unavailable snapshot on store failure         |
| Small skills/bootstrap                     | Pi already discovers skills and runs tools but needs the specific memory contract                                                           | Static English resources, no personal memory; native disable/remove                         |
| Generation-bound pages                     | Bounded reads otherwise silently skip under mutation                                                                                        | Query/view/record/generation binding; invalidated continuation must restart                 |

The P2 review correction adds a public Core `authorizeImport()` preflight: Pi can
report a model switch but cannot apply this workspace's Core authority before a
filesystem read. It delegates to the existing Core policy; the synchronous adapter
calls it before `importFile`, and capture retains its own guard. No new policy,
capability token or service is added. This relies on the stated single-writer,
synchronous boundary and does not establish OS isolation.

Observed `retained_excerpt` and imported text now share the existing read-range
contract. `Array.from` supplies Unicode code-point iteration; Core supplies exact
revision selection and bounded continuation metadata, which Pi/model prose cannot
supply durably. No new parser, input restriction or schema migration is needed.
The SDK read/UUID spy and tail-fixture script are developer-only observers/fixtures,
needed to prove absence of pre-denial processing and genuine tail retrieval. They
are neither normal product tools nor model replacements. See `P2-VALIDATION.md`.

No custom planner, translator, search service, installer, notification system,
credential store, universal schema, workflow DSL or external recovery service exists.
Development tooling: TypeScript, tsx, ESLint/typescript-eslint, Prettier and
dependency-cruiser supply native checks; they are not runtime product features.

## Safety and declared limits

Ordinary personal deployment is trusted, including Pi's current user-selected model;
no automatic routing extension is supported. Any observed model change blocks new
managed processing in this first block. A later recipient-confirmation workflow is
outstanding; the adapter never switches models. RPC tests identify a synthetic
controller, never the actual owner or owner approval. Input capture certifies only
the observed hook stage, not original keystrokes. No consequential operation is
implemented, so no reusable approval boolean exists.

The explicit first unimplemented R1 capability is nested/terminal Work with
dependencies and partial waits. Also outstanding: other four kinds, Methods/Runs,
Concept/Entity navigation, FTS/structural search, general correction lifecycle,
Signals/Evaluations, managed effects and exact approvals, claims beyond one writer,
export/backup/quarantine restore and epoch reconciliation, archive/deletion,
PDF/EPUB, full access policy and provider-switch qualification, scale/independent
T30 and owner trial T31. Schema 1 rejects unknown/newer schemas; there is no migration
or raw database replacement support. A raw copy/rollback is unsupported. An import
may leave safe unreferenced staging/material files; no GC is advertised. Fsync and
readback do not establish hardware power-loss safety. Disk-full simulation and
logical injected interruptions are narrower than physically exhausting the disk.

END_OF_FILE: docs/DEVELOPMENT.md
