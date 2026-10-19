# Zaratustra — first installed continuation block

A development Pi package with one extension, English bootstrap and two small skills.
Through conversation, the model saves Activity/Work, exact original Evidence and
English Knowledge; a fresh process can discover the continuation from disk.
Small permitted UTF-8 TXT/Markdown materials have immutable retained bytes and
addressed reads. This is an early block, not full R1 or a production release.

Qualified profile and exact public candidate are recorded in `docs/EVIDENCE.md`.
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
Daily use is conversation only: ask to create an area, send a material, or continue.
The user does not enter internal identifiers or edit service files.

`pi update --extensions` reconciles the configured pin. Bare `pi update` updates
the host instead. Explicit upgrade selects a different real public commit with
`pi install`; no mutable-branch assumption. `pi remove <same-source>` removes
package configuration/resources while the separate workspace remains. Native
package filters `extensions:[]` and `skills:[]` disable both resources.

Developer commands: `npm ci`, `npm run check`, `npm run deliver`. See `AGENTS.md`
and `docs/DEVELOPMENT.md`. Source tests use synthetic directories outside checkout.

END_OF_FILE: README.md
