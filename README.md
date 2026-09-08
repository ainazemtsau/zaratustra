# Zaratustra

Version **0.5.0**, Work 5: `zara init` creates a local workspace;
`zara migrate` explicitly adds schema 4; `zara records create` stores initial
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

For the current run, follow [installation and walkthrough](docs/work5/INSTALL.md).
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
effect, not late availability of referenced bytes. Context, submit_result and
next Work remain Works 6–8.
M0 is not closed; no personal workspace is selected.

Read [lifecycle decisions and W19–W27](docs/work5/PLAN.md) before later work,
and [Product RESULT](RESULT.md) for exact commits and runtime evidence.
Setup evidence remains under docs/setup/ as history. Windows is the observed
platform; Linux/macOS and an independent participant's installation remain unverified.
CI/CD, GitHub Actions and notifications are excluded until a separate owner request:
[owner receipt](docs/setup/OWNER-DECISION-20260907.md). Public hosting is future work.

END_OF_FILE: README.md
