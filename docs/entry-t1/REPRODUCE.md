# Entry T1 feasibility evaluator

This development-only evaluator exercises the installed wheel through public Core
exports on a newly created disposable workspace. It uses explicit generic demo
records and no Process Pack or test fixture.

From the repository, after dependency preparation, choose a new ignored output
directory:

```text
uv run --locked python -m tools.probe_entry_t1 --output _scratch/entry-t1-run
```

The command builds and installs the wheel in an isolated environment under that
directory. One child process explicitly migrates the fresh workspace through the
current schema 7, obtains authorization through
the trusted development application channel, and publishes exact new bytes. It
then exits before acceptance. A second child validates the preserved originating
revision and publication receipt, accepts the exact reference, opens the bounded
context, and verifies that repeated recovery discovers the same receipt without a
second effect.

A copied interrupted workspace receives a separate authorized mutation. Recovery
must refuse that revision as foreign; an attempted transport-only refresh still
fails Core's immutable Handoff `source_revision` check. The retained `summary.json`,
`evidence/states/*.json`, receipts, preserved Handoff, exact context bytes, and
subprocess transcript expose the observed states and operations.

This proves feasibility of a trusted scripted composition over the current Core.
It does not provide the end-user entry shell, perform the real ChatGPT-to-Codex T6
pass, establish personal usefulness, or constitute owner acceptance.

END_OF_FILE: docs/entry-t1/REPRODUCE.md
