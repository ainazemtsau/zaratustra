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

Core/app0.3 supports data protocols0 and1 and requires protocol1 for verified late
Sleep succession. A compatible update verifies an exact pre-upgrade snapshot,
then atomically records protocol1 without recreating Activity/history/refs. Old
Core0.2 refuses the upgraded root before mutation. Interrupted runtime publication
can be completed by re-entering through the verified new package; the committed
data protocol is never silently downgraded. This is mechanical format evolution,
not semantic migration of personal content.

Install this Pi package and run `/zaratustra`. First use bootstraps the two
verified Python wheels using uv/Python; the command then returns to ordinary Pi.
Pi owns the model, chat, authentication and builtin coding tools. There is no
child chat, editor loop, required daemon, or model-send cap in the normal path.

Write normally. The extension retains exact human input, supplies authoritative
Core context, and exposes `zara_context`, `zara_route`, `zara_change` and
`zara_result`. Route chooses a versioned Activity and scoped Work atomically.
Result stages outputs/changes only; the actual assistant final is retained and
committed at Pi's stable `agent_settled` boundary. Plaintext stays plaintext.

`/reopen` in a fresh Pi session reloads the same Core conversation without replaying tools. `/zara-reply TEXT` addresses the exact current Core question; ordinary input never consumes a pending wait. Bare `/zara-sleep` considers retained sources across all Activities and unassigned work, without an Activity prerequisite or picker. Its ordinary Work belongs to the workspace; source ownership, goals and rights stay where they were. Global memory and chosen Methods can support subsequent work. A correction intended for a local Activity without destination permission stays a targeted proposal; it is not silently made universal. `/zara-cancel` explicitly cancels an incomplete Core Work while preserving uncertainty about external effects. Hook failures are visible and
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

Native tool replies use Pi's public 50 KiB presentation budget, including UTF-8,
JSON escaping and reply metadata. History replies expose an explicit projection
of whole sources: the cutoff and source hashes stay exact, the cursor advances
only across delivered sources, and `has_more` includes withheld material. A single
source that cannot fit is `NOT_DELIVERED`; a smaller page cannot split it. Other
oversized reads report missing delivery explicitly. Successful mutations retain
their actual acknowledgement even when accompanying context cannot be presented.
This changes no Core record or receipt and claims no analysis of omitted material.
It is not a total-context or token guarantee: repeated bounded reads can still
fill the model context. Provider failures remain incomplete; no automatic retry
is performed. Required pinned context supplied before execution is not truncated.

Sleep/history presentation decodes only known protocol message and observation
base64 fields into exact UTF-8 source data. The view includes codec provenance
and the original Core source reference/hash, without a second encoded copy.
Unsupported binary, invalid UTF-8 or noncanonical encoding stays explicitly
marked and encoded; it is not presented as decoded or analysed text. Arbitrary
record bodies are not recursively decoded. This reversible display changes no
Core material, receipt, Method or authority; source text is evidence, not a new
instruction from the adapter.
Sleep's initial display checks the full context view's UTF-8 JSON size against
1 MiB. If decoding expands it past that boundary, the complete original encoded
context is supplied once with an explicit decoded-not-delivered marker. If even
that marked fallback cannot fit, execution stays incomplete before a provider
send. This presentation check is separate from model context/token capacity and
does not change Core's original preparation guard or retry an Attempt.

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

