# Zaratustra

## Work journal, decisions and revisions (0.19)

In a connected Pi Process, agree on keeping a useful work journal and speak normally:

- “Read this failed check, explain what is known, and suggest the next step.”
- “Save this decision: postpone the format change until the source is checked.”
- In a new chat: “Why did we postpone that change? Show the source.”
- “Correct the explanation; the file was unavailable.” The decision remains accepted.
- “Replace the decision with this one.” Previous content and authorization remain visible.
- “Share only this conclusion,” or “Export these records with their evidence.”

The installed agent instruction uses registered episode/decision/document operations.
Saved sources stay pinned to their historical version. Default writes are local;
shared Home conclusions do not disclose local evidence to another Process. Search
uses fields, links and FTS5 with agent reformulation; it does not guarantee semantic
or Russian morphological matches. The agent opens found sources before answering.

Standalone package reading: `zara-home inspect-export <package.zip>`; exact contents
can be opened with `--reference '<JSON reference>'` or the common export.read API.
See [Stage 2A implementation](docs/stage2a/IMPLEMENTATION.md) and
[observed checks](docs/stage2a/VERIFICATION.md). Local skills management is still 2B.

## Home and standalone Processes (0.18)

With the installed Pi connection you can ask:

- "Create Study Notes for collecting reading material. No tasks."
- "Put Study Notes and Experiments in Learning, and Study Notes also in Personal."
- "Connect them with a related_to relationship. Save this document in Study Notes."
- In a **new chat**: "Show Learning, open Study Notes and read the saved document."

Home is a SQLite registry. Each Process has its own workspace and database. A new
Process starts with title/purpose and **zero Works**, Packs or Results. Groups have
many-to-many membership; relationships have explicit types. Saved content persists;
unsaved conversation is not memory. No Direction OS workflow runs inside a Process.

### Install and connect

Install a reviewed checkout with `uv sync --locked --no-dev --no-editable`, or
install its built wheel into a dedicated Python 3.13 environment. Keep that program
environment: the exported connection uses its absolute interpreter. Publication
evidence is in [RESULT.md](RESULT.md); do not infer public availability from this
README. Home and Process data live outside the program checkout.

Your agent performs setup after you choose the folders. Both folders must exist;
they can already contain your files. Unrelated files and settings are preserved.

```powershell
zara-home setup --home '<chosen Home>' --directory '<Pi chat folder>' --agent pi
# Direct entry to the SAME Process and Home:
zara-home setup --home '<chosen Home>' --directory '<Process folder>' --workspace '<Process folder>' --agent pi
# Same operations and databases from Codex:
zara-home setup --home '<chosen Home>' --directory '<Codex chat folder>' --agent codex
```

Start a new Pi chat in the connected folder and approve its local extension when
Pi asks. The shipped `zaratustra` tool is discovered under `.pi/extensions`.
Codex uses `.agents/skills/zaratustra-home/SKILL.md`; invoke `$zaratustra-home` if
discovery is not automatic. Every new chat reads `.zara-context.json`; the owner
does not repeat paths. Neither export changes global agent settings.

### Existing data and updates

Keep the previous program environment while installing the next version. Run the
same setup from the new installation with `--update-connection` to update only an
unmodified connection previously exported by Zaratustra. Edited connections and
different context selections refuse; user settings are never replaced.

Ask the agent to import an old catalog with `catalog.import`. Original bytes remain
intact, aliases and unavailable registrations are retained, and updated legacy APIs
refuse further writes to that retired catalog. Retry an interrupted import into
the same Home. Never run an older product writer against a retired catalog.
Read/import never migrate Process data. Explicit `workspace.upgrade` backs up the
SQLite database before schema10 migration; retain the backup and old installation
for recovery. Do not use old code on new schema10 databases.

Ask the agent to update a moved Process's location: it verifies the same identity.
Missing/replaced folders stay visible as unavailable/mismatched, with cache clearly
separated from current facts. A registration_required result means creation already
happened: register that retained workspace instead of creating another Process.

See [Stage 1 boundaries and verification](docs/stage1/IMPLEMENTATION.md).

## Legacy Work-based entry

The following describes the preserved earlier path. It is not a prerequisite for
standalone Processes; use Home above for those.

T4 adds a common installed entry and thin standard Codex / Claude Code skills.
The commands below install the exact implementation commit named in the
[T4 report](docs/results/2026-09-15-core-activation-entry.md), once that commit has been published with authorization.
This README does not attest public availability; consult the dated publication
evidence for that exact pin in the report. A failed fetch is a
blocked public install: do not replace the pin with `main`, `latest` or an older SHA.
Local built-wheel proof is described in the [T4 plan](docs/public-onboarding-r2-t4/PLAN.md).

From a new empty PowerShell folder, with Git and uv available, paste the full
`implementation-commit` from that exact T4 report. Keep the report with this README;
a different report or a moving branch is not an installation pin. These commands
stop on failure. No personal data folder is selected by installation.

```powershell
$candidate = Read-Host 'Full 40-character implementation-commit from the T4 report'
if ($candidate -notmatch '^[0-9a-f]{40}$') { throw 'An exact commit is required' }
if (@(Get-ChildItem -Force).Count -ne 0) { throw 'Start in a new empty folder' }
git init program
if ($LASTEXITCODE -ne 0) { throw 'git init failed' }
Set-Location program
git remote add origin https://github.com/ainazemtsau/zaratustra.git
if ($LASTEXITCODE -ne 0) { throw 'remote setup failed' }
git fetch --depth 1 origin $candidate
if ($LASTEXITCODE -ne 0) { throw 'Exact public pin unavailable; stop here' }
git checkout --detach FETCH_HEAD
if ($LASTEXITCODE -ne 0) { throw 'checkout failed' }
if ((git rev-parse HEAD).Trim() -ne $candidate) { throw 'Wrong program commit' }
uv sync --locked --no-dev --no-editable
if ($LASTEXITCODE -ne 0) { throw 'Locked installation failed' }
$python = (Resolve-Path .venv/Scripts/python.exe).Path
$zara = (Resolve-Path .venv/Scripts/zara.exe).Path
$zaraAgent = (Resolve-Path .venv/Scripts/zara-agent.exe).Path
Set-Location ..
& $zara entry ready
if ($LASTEXITCODE -ne 0) { throw 'Program readiness failed' }
```

Keep this immutable program folder. Installation creates no catalog or Work.
The runtime reports its actual version, Python and package paths. Git HEAD and the
report identify the source pin; the runtime does not attest Git or public availability.
Updates/recovery across releases remain a later task. Windows is the observed platform.

Export a standard connection into a **new** chat folder whose parent exists:

```powershell
& $zara entry connection codex ./codex-chat
# Or choose Claude Code and a different NEW folder:
& $zara entry connection claude ./claude-chat
```

Open the chosen chat folder in the corresponding agent. In Codex CLI invoke
`$zaratustra` (or select the skill); in Claude Code invoke `/zaratustra`. The shipped
files use [Codex's local skill format](https://learn.chatgpt.com/docs/build-skills)
and [Claude Code's skill format](https://code.claude.com/docs/en/skills).
Exports refuse existing folders. A partially failed export must be inspected and
retained; retry in another new folder. Nothing writes to global agent homes.

In every fresh chat, provide the exact catalog path and designation, for example:
“Use Zaratustra; my catalog is `<chosen path>/catalog.json`, designation `<my name>`.
Show readiness and resume.” The agent must reread those explicit inputs. It cannot
infer a workspace from chat history or pick a historical Work. Readiness reports a
file comparison for the chosen connection, not proof that the agent loaded it.

If skill discovery or PATH invocation fails, read the exported SKILL.md explicitly
or use the absolute Python printed by readiness. The same fallback works from any
folder, including a fresh terminal (replace the path below with that actual path):

```powershell
$python = Read-Host 'Absolute installed Python path printed above'
& $python -I -m zaratustra entry ready
& $python -I -m zaratustra entry ready --connection codex --connection-root ./codex-chat
& $python -I -m zaratustra.trusted_chat.agent read '<chosen path>/catalog.json' '<my name>' --actor 'codex-local' --source-ref 'current-owner-message'
```

Replace `codex` / `codex-chat` with `claude` / `claude-chat` for Claude Code.
`zara-agent read` is the ordinary trusted local-agent path for one exact catalog and
designation. It binds an active Process read to the fresh Core query and requires no
separate approval form; actor and source reference are agent-supplied provenance for
the current owner request. A refusal leaves current Work unknown; `no_current_work`
is a successful Core answer. Missing selection returns nonzero without discovery.

For a new Process, give ordinary prose: its title, need, desired outcomes and
constraints. `zara-agent draft --help` shows those string arguments; choose the catalog
location and designation explicitly. The product owns its saved catalog and journals;
you do not author JSON. A fresh `zara-agent read` resumes the same saved prose and next
manual action through
draft, research, proposal and activation. Definition authoring remains assisted and
bounded by the installed supported contract; research is not automatic. Review every
activation/change preview and give each separate requested effect a genuine decision
in conversation. For a saved supported proposal, `zara-agent activation-preview
<catalog> <designation> <workspace>` shows the proposed Process and selected location
without bootstrapping Process records. After the owner says to create that exact
proposal, the trusted assistant runs `activation-confirm` with the preview's
assistant-held digest plus current host provenance. The owner never handles that
digest or a technical payload. Changed intent refuses before bootstrap; an explicitly
selected initialized empty workspace keeps its identity. An interrupted activation is
resumed by showing a fresh preview of the same retained plan. Other effects remain on
the existing confirmed paths.
No-current is normal; a later Work is an explicit separate choice.

Version **0.17.0** is a technical foundation preview. It implements durable local
workspaces, authorized mutations, versioned artifacts, accepted-result handoff,
bounded Work context, Result/next Work, external process-pack binding, seven
process read capabilities, a shared overview, explicit entry discovery/basic read,
and recoverable exact preview/publication/acceptance of new external text material,
plus a modest installed first-use/manual external-chat path and a bounded immutable
process-definition adapter, Process material/terminal Results, truthful Process
current-or-no-current reads and explicit later ordinary Work admission. See the
[current report](RESULT.md), [T1 process plan](docs/process-t1/PLAN.md),
and [first-use plan](docs/entry-t5/PLAN.md).

This version does **not** provide a full interactive method constructor,
provider-integrated external research, personal memory, model routing or a graphical
UI. Its generic first-use command deliberately creates unbound Core metadata instead
of inventing a production Process Pack.
The two fictional processes used to verify the pack contract are development
fixtures under `tests/fixtures`; they are not installed product templates.
Publication of this foundation is not a claim that it is ready for everyday use.

The T1 process adapter is a public Python seam, not a new CLI or scheduler. It validates
one exact immutable definition edition and canonical result snapshot, exposes ready and
blocked domain nodes with exact predecessor data/reasons, and projects one deterministic
eligible occurrence onto the existing focused Core Work. Recurrence creates a numbered
occurrence instead of a dependency cycle. The two mechanical definitions used to test
this behavior remain under `tests/fixtures/process_creation` only. Read the [T1
readout](docs/process-t1/READOUT.md) for its explicit limits.

Public onboarding R2 T2 is also a Python seam, not a planner or onboarding wizard.
`read_process_state` derives the unique draft/ready Work or normal no-current state
and explicitly refuses corrupt many-current history. After a terminal Result, a
trusted host may use `process_packs.work_creation_request` and `create_later_work`
to revalidate an exact installed Pack and submit one separately authorized ordinary
Work to Core. Schema 9 records that effect without changing released migrations or
old events. Read the [bounded T2 plan](docs/public-onboarding-r2-t2/PLAN.md).

The underlying M0 foundation: `zara init` creates a local workspace;
`zara migrate` explicitly upgrades the schema; `zara records create` stores initial
Process, draft Work, declared Artifact and Event records with revisions.
`zara status` and `zara records read` read persisted facts in later invocations.
The installed engine and the workspace are separate directories.

Requires uv and managed Python 3.13.7. From this repository:

| Step | Command |
|---|---|
| Prepare | `uv sync --locked` |
| Full check and build | `uv run --locked python -m tools.check` |
| Check delivery report too | `uv run --locked python -m tools.check --deliver` |
| Isolated installation and restart proof | `uv run --locked python -m tools.probe_install` |
| Enable local commit guard | `git config core.hooksPath .githooks` |

The full check runs formatting/lint, types, module boundaries, tests and wheel/sdist
build. The installation probe installs the wheel with locked runtime dependencies
in a disposable environment outside checkout, runs the real `zara` executable in
separate processes, then cleans up its own temporary folders.

For the M0 Handoff walkthrough, see [Work 5 installation](docs/work5/INSTALL.md).
Run the installed commands in a newly created empty folder, or name that folder:

```text
zara --version
zara init
zara status
zara init
```

The three workspace commands print the same persisted metadata. Repeating `init`
on a valid workspace reads it without rewriting the DB. Nonempty unrelated folders,
unknown schema versions and incomplete workspaces are refused without repair.
`status` never creates a workspace. No parent-folder discovery is performed.

Workspace layout follows the accepted plan:

```text
chosen-folder/
  .zara/state.sqlite3
  processes/
  artifacts/
  projections/
  inbox/
```

`init` still creates schema 1; `migrate` explicitly upgrades it without changing
workspace identity/time. Initial records can be created once in an empty record store.
Work starts as a draft without permissions; Artifact has no published file or active version.
`zara mutate` confirms an exact internal operation in the local console, then Core
checks current Work/rights, revision, duplicate identity and references, and commits
the change/event/receipt together. `zara receipt` checks current read rights;
`zara history` is the owner's local audit view. With explicit Artifact scope,
`publish_artifact` publishes immutable bytes with SHA-256, then commits their
registration and active version. `artifacts read` verifies bytes on every read;
`restore_artifact` repairs exact registered content through the same Mutation API.
`projections status` and `projections rebuild` inspect/recreate the deterministic
overview from DB without another state change. These are owner-local inspection
surfaces. `zara migrate <workspace> --to 5` explicitly enables Handoff storage.
`zara handoff import <workspace> <file>` (or `-` for UTF-8 stdin) obtains separate
exact console confirmation and records accepted_result with provenance through
the same Mutation API. `zara handoff list <workspace>` reads saved acceptances;
`zara handoff schema` prints the portable JSON schema. A receipt records the prior
effect, not late availability of referenced bytes. Work6 provides authorized
`work open`; Work7 adds schema6 and atomic `result submit`/next Work.
`zara migrate <workspace> --to 7` admits exact pack binding explicitly;
the default target remains 4. T2 package use is through the public Python API.
T3 adds `process_packs.read_capabilities`: seven derived answers over an exact
authorized metadata scope, with separately authorized selected Work context.
Read [the capability contract](docs/m1-capabilities/PLAN.md) and
[the reproducible example](docs/m1-capabilities/REPRODUCE.md).
Entry T3 adds `zara entry intake`: it resolves one explicit catalog selection,
validates a strict external-material envelope and current Work/basis/rights, displays
the full exact material and two planned operations for trusted confirmation, then
uses standard Artifact publication and Handoff acceptance. Its receipt keeps input,
publication, acceptance and Work completion distinct; this bounded feature never
completes Work. Entry T4 adds a non-authoritative coordinator journal and authorized
Core receipt/content recovery while the exact original plan remains journaled.
Repeated or restarted delivery then returns the original stage receipts and saved
continuation without rebasing the original intent; a later standard Result is
displayed separately as the current terminal continuation. If the whole original
journal is lost after state advances, preparation refuses rather than inventing an
original wrapper from current facts. See [the installed recovery
reproduction](docs/entry-t4/REPRODUCE.md).
Entry T5 adds `zara entry start`, which accepts user-facing generic setup JSON and
initial UTF-8 material, creates/registers one explicitly designated instance, and
uses the four ordinary confirmed Core operations to make its initial material an
accepted basis. `zara entry open` resolves current bounded context without user
handling identities or revisions. In 0.12.1, `zara entry request` saves a copyable
provider-neutral request with a mechanically decoded readable UTF-8 rendering of the
exact Work goal and every accepted saved version, plus the unchanged complete Core
context and original basis identities/hashes. Existing version-1 request files from
0.12.0 remain valid for receive and same-intent recovery. `zara entry receive` wraps
returned text and reuses the strict recoverable intake confirmation without refreshing
the saved request. No command contacts a provider. Follow the [installed first-use
walkthrough](docs/entry-t5/REPRODUCE.md).
M0 remains partial; no personal workspace is selected.

Read [pack lifecycle decisions and W15–W20](docs/m1-packs/PLAN.md) for immutable
Process/Work version binding and missing/incompatible-pack behavior. Registration
and pack reads currently use the public Python API; this is not an interactive
process-creation flow. Read [Product RESULT](RESULT.md) for the retained T6 evidence.
Setup evidence remains under docs/setup/ as history. Windows is the observed
platform; Linux/macOS and an independent participant's installation remain unverified.
CI/CD, GitHub Actions and notifications are excluded until a separate owner request:
[owner receipt](docs/setup/OWNER-DECISION-20260907.md). The owner authorized public
hosting and integration into `main` on September 11–12, 2026; that authorization
does not enable CI/CD, notifications or access to a user's workspace.
The repository does not currently include a distribution license.

END_OF_FILE: README.md
