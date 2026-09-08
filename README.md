# Zaratustra

Version **0.2.0**, Work 2: `zara init` creates a local workspace;
`zara migrate` explicitly adds schema 2; `zara records create` stores initial
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

For your first run, follow [installation and trial instructions](docs/work2/INSTALL.md).
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
Work is a draft without permissions; Artifact has no published file or active version.
Updates, operation-id/replay, Handoff, permissions, context and artifact files require Works 3–8.
This release does not complete T1 or M0. No personal workspace has been selected.

Read [record decisions and W19–W27](docs/work2/RECORDS.md) before later work,
and [Product RESULT](RESULT.md) for exact commits and runtime evidence.
Setup evidence remains under docs/setup/ as history. Windows is the observed
platform; Linux/macOS and an independent participant's installation remain unverified.
CI/CD, GitHub Actions and notifications are excluded until a separate owner request:
[owner receipt](docs/setup/OWNER-DECISION-20260907.md). Public hosting is future work.

END_OF_FILE: README.md
