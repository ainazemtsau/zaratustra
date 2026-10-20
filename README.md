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

Current qualification/evidence: [E1](docs/E1-VALIDATION.md), [reproduction](docs/E1-REPRODUCE.md).
Accepted D evidence remains [here](docs/D-VALIDATION.md). Accepted C predecessor
and remaining release obligations: [R1 status](docs/R1-STATUS.md).
Full target: [specification 1.1](docs/specification-v1.1.html).

Operator installation in an isolated PowerShell environment:

```powershell
$env:PI_CODING_AGENT_DIR = '<absolute isolated Pi config directory>'
$env:ZARATUSTRA_HOME = '<absolute separate durable workspace>'
$env:ZARATUSTRA_IMPORT_ROOTS = '["<absolute permitted input directory>"]'
pi install git:github.com/ainazemtsau/zaratustra@<exact-public-commit>
pi list
pi
```

Use Pi's normal authentication and deliberately selected model. Never copy
credentials into this repository. ZARATUSTRA_HOME is trusted operator setup, never
a model tool argument; it must remain outside the checkout/package/Pi cache.
Daily use is conversation only: ask to create an area, send a material, recall useful
resources, plan using their current conditions, correct a record, or continue.
Ask to save a useful approach; a later suitable task can discover and reuse it without
a manual reminder. Correct it through conversation while keeping old applications exact.
The user does not enter internal identifiers or edit service files.

`pi update --extensions` reconciles the configured pin. Bare `pi update` updates
the host instead. Explicit upgrade selects a different real public commit with
`pi install`; no mutable-branch assumption. `pi remove <same-source>` removes
package configuration/resources while the separate workspace remains. Native
package filters `extensions:[]` and `skills:[]` disable both resources.

Developer commands: `npm ci`, `npm run check`, `npm run deliver`. See `AGENTS.md`
and `docs/DEVELOPMENT.md`. Source tests use synthetic directories outside checkout.
E2 retains exact confirmations, managed actions/recovery and SKILL.md export/drift;
E3 retains user backup, verified restore, retention/archive/delete. Codex and Sleep are later.

END_OF_FILE: README.md
