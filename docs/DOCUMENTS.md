# Managed Activity documents

Owner-authorized implementation, 23 October 2026; Pi 1.4.0. The owner requested quick
mechanical checks only, no lengthy qualification or live model/API conversations.

Files below `<trusted project>/activities/` hold canonical Markdown contents. Existing
resource Entities register document identity/path/type/state, exact immutable Evidence
head, pinned optional format and document links. No Activity-specific table, editor,
daemon, model, automatic Git or launcher. No real Health migration is performed here.
`zaratustra-documents` defines the common agent procedure; folders are created lazily.

## Operations

- `zara_document_preview` + existing exact `zara_confirm` + `zara_document_apply` create,
  update, rename/move, archive, remove or restore working documents. Apply coordinates
  the public Pi write engine and existing intent/observation/receipt machinery.
- `zara_document_inspect` compares permitted registry/current bytes without adopting.
- `zara_browse` documents/documents_archive/documents_removed uses existing access,
  pagination, history and search machinery. Registry kind is entity; contents are Evidence.
- `zara_documents_publication` checks explicit version closure, hashes and pending
  registrations and returns an index/manifest plan. It does not write, back up or push.
  Ordinary Pi file/Git operations publish the checked set. Historical exports are copies.

Normal service metadata stays in SQLite. One stable ID comment survives ordinary edits.
Optional exact formats use standard JSON Schema 2020-12 in one fenced JSON block;
structured data likewise occupies one JSON block in Markdown. Ajv 8.20.0 validates
structural keywords, without network schema loading, async validation or format plugins.
Format definitions are immutable Evidence versions; the model chooses schema/migrations.
No promise of semantic or domain correctness follows from schema validation.

Schema 8 introduces no new tables. It prevents old writers from stripping document
metadata. The existing verified backup/receipt/manifest-repair migration covers 7→8;
older supported workspaces migrate through their existing steps. E3 schema-8 bundles
include document snapshots because they are ordinary retained original materials.
Restoring the database does NOT roll back live working files. Inspect drift and reconcile
before continuing; old-epoch operation replay cannot perform cleanup or other mutations.

File writing and SQLite registration are separate durable stages, not one cross-resource
transaction. Pending operations are discoverable; retry finalization by original request ID
without replaying native writes. A failed/mismatched finalization remains pending/unknown.
One qualified trusted writer, local ordinary files, no hostile OS-race/isolation guarantee.
Native postconditions do not prove exclusive author identity.

Archive preserves content. Remove deletes the working file, not historical snapshots or
Git commits. Open Work/problems/active document dependencies block removal. Existing E3
retention/deletion operations govern full body purge. Moves cannot silently repair prose
links; the agent must inspect/update affected current documents before publication.

Each controlled document is limited to 64,000 UTF-8 bytes, reusing the existing file bound.
Split journals/materials into addressed files; no unbounded-file/recall promise. Copying an
active SQLite alone is unsupported; use the verified memory backup for a device handoff.
No simultaneous cross-device merging is implemented. Credentials/host configuration stay
outside portable memory. Personal data and user Git policy remain owner controlled.

Quick checks: `npx tsx --test tests/documents.test.ts`, selected P2 regressions, tsc,
ESLint on changed source/tests, Prettier on changed files and build. No full `check`,
`deliver`, scale/fault matrices or native model conversations under this assignment.

END_OF_FILE: docs/DOCUMENTS.md
