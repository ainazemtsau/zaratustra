# Zaratustra in ordinary Pi

Install a built package once with `pi install /absolute/path/to/package`.
Keep that directory: Pi loads local packages from their installed paths. The source
folder alone is not a distribution; build it with
`python -m tools.build_permanent_package --output /absolute/path/to/package`.
The builder includes verified Core/app wheels and pinned dependency hashes.

The tested host is Pi 1.3.0 with Node 22 and `uv` on PATH. First entry lets uv
provision Python 3.13.7 and pinned dependencies; download access is needed unless
compatible dependency wheels are bundled. Pi keeps its own authentication.
Runtime code uses Python and TypeScript without PowerShell. Windows entry is
tested here; macOS/Linux are portable targets, not native-test claims.

Install this Pi package and run `/zaratustra`. First use bootstraps the two
verified Python wheels using uv/Python; the command then returns to ordinary Pi.
Pi owns the model, chat, authentication and builtin coding tools. There is no
child chat, editor loop, required daemon, or model-send cap in the normal path.

Write normally. The extension retains exact human input, supplies authoritative
Core context, and exposes `zara_context`, `zara_route`, `zara_change` and
`zara_result`. Route chooses a versioned Activity and scoped Work atomically.
Result stages outputs/changes only; the actual assistant final is retained and
committed at Pi's stable `agent_settled` boundary. Plaintext stays plaintext.

`/reopen` in a fresh Pi session reloads the same Core conversation without replaying tools. `/zara-reply TEXT` addresses the exact current Core question; ordinary input never consumes a pending wait. `/zara-sleep` selects the current Activity or offers readable choices, then examines retained outcomes and adapts its memory/methods. `/zara-cancel` explicitly cancels an incomplete Core Work while preserving uncertainty about external effects. Hook failures are visible and
leave incomplete Work open. Unknown previous tool effects require reconciliation;
this adapter never automatically retries them. Core protects its own mutations
with CAS, fencing and receipts. Pi builtin file/shell effects are retained as
observations only: they are not Core transactions or exactly-once effects.
An interrupted run may need explicit reconciliation before another Core Work.

Data lives in the selected `ZARATUSTRA_HOME` (or platform application data).
Host correlation is stored as reserved Core data, not a second authority file.
The operating system releases the mechanical host lock after a crash.

`/zara-review` starts a fresh Pi session to review the latest completed delivery
in the same Activity with read-only tools. `/zara-owner-result` presents the
delivery and matching report, then records the owner's explicit verdict.
Neither a successful check nor a model review constitutes owner acceptance.
`/zara-status` shows pending work. Pi's history is a client view; Core supplies
durable context after reopening. Normal production work has no artificial model
call/token/money cap; finite bounds are explicit evaluation settings only.

Keep the same data home across code updates. Let Pi become idle before reloading
the extension; retained Work and waits remain in Core. Pi identifies a local package by its
absolute registered path: installing another version in a new folder does not
replace the old registration, even when the package name is identical. For a
new-folder update, unregister the old path and register the new path in the same
scope. In ordinary Pi, with `pi` available on PATH, run these mechanical commands:

```text
!pi remove "/absolute/path/to/old-package"
!pi install "/absolute/path/to/new-package"
/reload
/zaratustra
```

These are Pi's shell escape and its existing reload command; there are no
`/install` or `/remove` slash commands. From a terminal the equivalents are
`pi remove` and `pi install`, then restart Pi. If the original registration used
project-local `-l`, use `-l` on both package commands. Removal only unregisters the
local path; it does not delete that folder or the external Core data. Keep the old
folder until the new package has opened successfully. For a first install inside
an already running Pi, use `!pi install "/absolute/path/to/package"`, then
`/reload` and `/zaratustra`.

Bootstrap checks exact schema compatibility,
preserves a technical pre-update snapshot, and only then selects the new runtime.
Activities, history, waits, credentials and references stay in place. The supported
update is schema-compatible 0.1.0 to 0.2.0; an incompatible schema refuses before
rewriting existing data. Future schema migrations are not claimed implemented.

Backup/recovery setup is outside the current minimal user flow. Continuing the
same Activities on several computers, synchronization and lost-source recovery
are deferred. GitHub source preservation does not upload private Activity data.
Do not share the data home or credentials.

END_OF_FILE: pi-package/README.md

