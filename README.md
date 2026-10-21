# Zaratustra — durable work, memory and textual Methods

A development Pi package with one extension, English bootstrap and two small skills.
Through conversation, the model saves Activity/Work, exact original Evidence and
English Knowledge; a fresh process can discover the continuation from disk.
Nested Work and addressed steps preserve dependencies, partial waits, results and lifecycle
history. Manual handoffs retain the original request and useful late/partial replies.
TXT/Markdown, text PDF and unencrypted EPUB keep immutable originals plus separately
addressed extracted text. New processes continue through chat without old transcripts.
Shared Concepts/Entities, English lexical/typed discovery and versioned corrections now
connect memory across activities. Full claims retain sources, states, conditions and times.
Textual Methods retain applicability, contracts and exact dependency versions; addressed
Runs keep meaningful episodes and real results. Evaluations separate technical/model/
reported feedback, and Signals retain unresolved problems plus independent reviews.
Reading, reported application, observed execution, ended episodes and usefulness are
different events. E1 does not finish full E/R1 or claim owner trial T31.

E3 adds verified SQLite/JSON bundles with raw managed materials, quarantine restore,
an external active epoch, restored-action reconciliation, archive, body deletion and
bounded cleanup. Restore remains available when the current database cannot open.
Every restored Work requires current-world reconciliation before effectful continuation,
including when the backup predates all action receipts. Archive is not deletion;
external backups, exports and Pi transcripts remain separate copies.

E3 design and scoped executor evidence: [design](docs/E3-DESIGN.md),
[validation](docs/E3-VALIDATION.md), [reproduce](docs/E3-REPRODUCE.md),
[actual chat demo](docs/E3-HUMAN-DEMO.md). Accepted E2 evidence is preserved in
[E2 validation](docs/E2-VALIDATION-094c0df4.md).
Accepted D evidence remains [here](docs/D-VALIDATION.md). Accepted C predecessor
and remaining release obligations: [R1 status](docs/R1-STATUS.md).
Full target: [specification 1.1](docs/specification-v1.1.html).

Install once in the project root, then start ordinary Pi there:

```powershell
pi install --local git:github.com/ainazemtsau/zaratustra@<exact-public-commit>
pi
```

Accept native Pi project trust after reviewing the package. No launcher, additional
AGENTS file or per-launch environment setup is required. With directory overrides
absent, Zaratustra creates `.local/memory`, `.local/imports`, `.local/output` and
`.local/backups` in Pi's current project directory. A fresh process in the same
folder reopens that memory; a different project has separate state. The snapshot
reports the actual paths. `.local` is permanent work data, not a disposable cache.
Memory, plans/history, retained originals and generated results are available to
ordinary Git versioning. You decide what to exclude and where to push. Zaratustra
does not create, edit or remove ignore rules, or automatically commit/push your data.
Existing manual ignore rules remain yours to change.

Use Pi's normal authentication and deliberately selected model. Never copy
credentials into this repository. Advanced explicit `ZARATUSTRA_HOME` deployments
keep their existing optional directory behavior and authority settings. Partial
directory overrides without a home fail rather than opening different memory.
See [startup behavior and reproducibility](docs/PROJECT-STARTUP.md) for limits,
native verification and explicit configuration.
This change makes saved files available to your own private Git workflow. It does
not add synchronization, multi-computer recovery or a running-system restore promise.
Daily use is conversation only: ask to create an area, send a material, recall useful
resources, plan using their current conditions, correct a record, or continue.
Ask to save a useful approach; a later suitable task can discover and reuse it without
a manual reminder. Correct it through conversation while keeping old applications exact.
The user does not enter internal identifiers or edit service files.
Full backup/export requires trusted setup with restricted:read; restore, full retained-
version body deletion and cleanup require restricted:read plus restricted:write.
An operator may preconfigure ZARATUSTRA_SCOPES as a JSON array containing those
scopes. Defaults remain empty. This administrative policy is fixed before bundle
inspection, independent of whether the database actually contains protected records.

`pi update --extensions` reconciles the configured pin. Bare `pi update` updates
the host instead. Explicit upgrade selects a different real public commit with
`pi install --local`; no mutable-branch assumption. `pi remove --local <same-source>` removes
project package configuration/resources while `.local` memory remains. Native
package filters `extensions:[]` and `skills:[]` disable both resources.

Developer commands: `npm ci`, `npm run check`, `npm run deliver`. See `AGENTS.md`
and `docs/DEVELOPMENT.md`. Source tests use synthetic directories outside checkout.
E2 supplies exact confirmations, managed actions/recovery and SKILL.md export/drift.
E3 qualification/acceptance is separate; full F/R1/T31, Codex and Sleep remain open.

END_OF_FILE: README.md
