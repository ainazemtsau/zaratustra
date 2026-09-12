# Reproduce installed incoming-material preview and acceptance

From this repository, choose a new ignored output directory:

```text
uv run --locked python -m tools.probe_entry_t3 --output _scratch/entry-t3-run
```

The probe builds the wheel, installs it with locked runtime dependencies in an
isolated Python 3.13.7 environment, and runs the copied exercise from an unrelated
directory. It creates one new generic schema-7 workspace and catalog row through
public product APIs. Normal Core operations authorize the Work and its Artifact and
publish a small generic prior basis.

The genuinely new report exists only in a new external JSON envelope before intake;
the probe verifies that no registered version has its hash. The installed coordinator
checks the exact selected identities, current revision, rights and basis bytes, saves
the complete preview, obtains trusted local-chat confirmation for that preview, then
uses ordinary `publish_artifact` and `accept_handoff` mutations. It verifies the exact
new bytes by their registered version and the exact accepted result/basis afterward.

The retained receipt distinguishes validated receipt of the input, publication,
acceptance and `not_requested` completion. The Work remains ready with no Result or
next Work. Adverse runs show that missing confirmation, a changed material payload,
an asserted approval field and a foreign target cause no effect before the successful
intake.

The output directory retains `summary.json`, `commands.json`, the external envelope,
catalog, disposable workspace, complete preview and receipt. These raw generic demo
artifacts remain ignored local evidence; none is committed.

For an already prepared catalog and a human-reviewed external envelope, the installed
interactive surface is:

```text
zara entry intake CATALOG DESIGNATION EXTERNAL_JSON
```

Use `-` only when a controlling terminal is available for confirmation. This command
does not contact or launch a research provider. Cross-invocation replay/recovery is
the next increment, not a guarantee of this one.

END_OF_FILE: docs/entry-t3/REPRODUCE.md
