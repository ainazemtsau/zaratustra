# Zaratustra

Version **0.11.0** is a technical foundation preview. It implements durable local
workspaces, authorized mutations, versioned artifacts, accepted-result handoff,
bounded Work context, Result/next Work, external process-pack binding, seven
process read capabilities, a shared overview, explicit entry discovery/basic read,
and recoverable exact preview/publication/acceptance of new external text material.
See the [current report](RESULT.md) and [transfer recovery plan](docs/entry-t4/PLAN.md).

This version does **not** yet provide an end-user process-creation assistant,
provider-integrated external research, personal memory, model routing or a graphical
UI.
The two fictional processes used to verify the pack contract are development
fixtures under `tests/fixtures`; they are not installed product templates.
Publication of this foundation is not a claim that it is ready for everyday use.

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
