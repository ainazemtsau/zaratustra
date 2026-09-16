# Stage 2A — approved scope and implementation

Owner authorized this unchanged scope on 2026-09-16 with «да», after the v3
comparison and the supplied seven clarifications. Base: Stage1 commit
079bf616cacbbea43a94537f7e6a89c674cc9086 (0.18.0). Candidate: 0.19.0.
The older Direction installation task is not closed by this product report.

## What a person can do

Work in an existing Process through Pi, agree once that the agent keeps a useful
journal, and ask ordinary questions. The agent saves substantial outcomes and
obstacles, opens exact evidence in later chats, and distinguishes its explanations
from the owner's accepted decisions. The same common API is available to Codex.

Example conversation:

1. “Read the failed report check. Until we verify the source, postpone changing
   its format; save that decision.” The agent records an episode under the agreed
   journal rule, saves a proposal and accepts its exact content under this instruction.
2. New chat: “Why did we hold off changing the report format?” The agent searches,
   opens the matching decision/episode and the exact source used then.
3. “The cause was an unavailable file. Correct the explanation.” A new episode
   revision appears. The accepted decision remains in force.
4. “Now replace that decision with a one-file format check.” A separate decision
   transition records the new commitment, reason and actual authorization source.
5. “Share only this short conclusion.” A separate Home-owned record refers back
   to the local version; another Process can read the conclusion but does not get
   the local log merely by following its link.
6. “Export these records.” The package includes history, schemas and pinned
   evidence in the selected export scope, plus explicit missing/excluded sources.
   The installed standalone reader opens it without a live Home.

## Common storage and registration

`zaratustra.journal.Registry` registers a stable type name and schema version,
Pydantic validation, supported operations, initial state and transition handler.
Episode, decision and document use this same interface. A test registers a fourth
type without modifying the Core union or storage. Handlers come from installed
Python code; serialized schemas never execute code or load handlers.

Every revision is one immutable Core ProcessMaterial with reserved MIME
`application/vnd.zaratustra.record+json`. Its envelope holds identity, logical
revision, owner scope, schema, content, pinned links, state, previous version,
reason, available authority/source and code-assigned recording time. The existing
save_process_material transaction commits these bytes with audit and receipt.
There is no parallel log file, extra domain writer or new Core database migration.
Core module bytes and released serialization remain unchanged.

Core state revision and logical document revision are deliberately distinct.
A record id stays stable; each appended version has its own material/operation id.
Operation retries with the same normalized intent replay; changed intent conflicts.
Updates require the logical revision read by the caller. A stale Process snapshot
also conflicts at Core. A post-commit projection failure reports committed data.
Store instances are read snapshots: open a fresh Store after a mutation.

## Documents and evidence

New editable documents use the registered document type, text or binary payload.
Raw evidence uses the existing material save/read API and remains immutable.
An old material can open as logical document revision 1 under its original id.
An explicit edit appends revision 2; it never changes, migrates or reuploads the
old stored bytes. Existing material links retain their exact meaning.

Ordinary record.read returns current content; a revision selects historical content.
Evidence references always include scope, kind, id and exact revision. A raw
material reference uses its original Core material revision, not logical revision 1.
The adapter returns bounded content pages with explicit next offsets.

## Decisions

Creation is a proposal. A proposal may be revised. Adoption requires its expected
revision and an available source describing the owner's actual authorization; it
cannot change content, title or links at the same time. Accepted content can only
be replaced or revoked through the dedicated operations, with a reason and source.
Replacement appends a linked revision preserving previous accepted content.
Revocation preserves content and history. Episode corrections never mutate decisions.

Host source_ref records the actual Pi tool-call reference or other live host source.
Authority source is a factual description supplied by the agent, not fabricated
message metadata or a cryptographic proof of owner consent. The trusted local
agent distinguishes owner instructions from discussion and saved untrusted content.
This continues the existing W21 local-owner boundary, not a hostile-agent sandbox.

## Scope and search

Default writes belong to the selected Process. Shared writes require explicit
sharing authority and belong to the selected Home. One internal Core workspace
under Home/.zara-home/shared backs this area; it is not registered as a user Process
and has zero Works. Its bootstrap is bound to the Home id. Read-only access never
initializes it. No personal Process, workflow or per-skill database is manufactured.

The command passes only selected Process and permitted shared stores to search
and source reads. A foreign reference returns scope_unavailable and does not fetch
the foreign source, title, content or neighboring records. A shared copy is a new
record linking the original exact version, never a second synchronized master.

Search builds a derived in-memory SQLite FTS5 index of current typed revisions in
those scopes, filtered by type, state or evidence link. It quotes literal Unicode
terms, searches prefixes with OR, and returns bounded snippets. It is rebuilt from
canonical data per call; no persisted second index can become authoritative.
The agent can reformulate or list filtered records and must open candidate evidence.
Russian morphology and arbitrary semantic similarity are not implemented. Old
unrevised raw materials are still listed/read by Stage1 operations, not FTS-indexed.
Large-history throughput is not a proven property of this initial full-snapshot path.

## Export and standalone reading

An explicit list selects 1..100 records and all their revisions. Exact evidence
links and previous-version links are followed only within the chosen export scope.
Shared evidence requires export_shared=true when exporting a local selection;
another Process is never auto-selected. Missing/excluded references are explicit.

ZIP entries contain UTF-8 structured record snapshots, inert schemas, exact material
bytes, identities, states, provenance and hashes. manifest.json lists selection,
scopes, schemas, edges and omissions. The reader verifies the inventory, identity,
hashes, schemas and reference closure without extracting archive paths.

`zara-home inspect-export <package>` opens independently of configured Home.
`--reference '<JSON pinned reference>'` opens an exact included source.
The shared API exposes read_export/load_export; Pi can use export.read and a pinned
reference. There is no live import, merge, full installation restore or schema execution.
Export creates a new file exclusively and never overwrites an existing user file.

## Delivery, checks and limits

The ordinary shipped journal skill is in src/zaratustra/journal/SKILL.md and is
included in both generated connections. Updating an existing unmodified connection
uses the existing setup --update-connection procedure. Local skill version management
is deferred to 2B. The agent chooses meaningful journal content; code ensures storage,
schemas and transitions, not the truth of its explanation or guaranteed retrieval.

Bounded contracts: 8 MB document bytes, 16 MB record envelope, 2 MB structured
command input, 1..100 results per page, 1000 export entries and 64 MB package.
Large binary evidence can retain the Stage1 file-save path. No new dependency,
paid service, vector platform, coordinator, autonomous executor or personal
Development content is part of this stage. Final observed proof is recorded in
VERIFICATION.md; scope approval is separate from owner acceptance of behavior.

END_OF_FILE: docs/stage2a/IMPLEMENTATION.md
