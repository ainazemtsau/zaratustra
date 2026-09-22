# Core v0.1 Stage 1 technical baseline

## outcome

The owner-approved Stage 1 boundary is implemented on `codex/core-v0.1` from
exact base `9913786eacb9c95ce103e29a21fa1e89dbdbd070`. Product authority now points
to the Core v0.1 baseline while preserving earlier CALLs and Works as history.

The Pi integration and DBOS durable-execution gates are both `inconclusive`.
Pi established exact request observation, pre-send refusal, strict JSONL framing,
busy-session questions and wait redisplay, but not compaction/overflow identity.
DBOS established real checkpoint recovery and durable queue behavior in the first
three scenarios, but the bounded Windows run did not complete scenarios 4–10.
Neither dependency is admitted to production, and implementation stops before the
Core v0.1 domain schema as required.

## evidence

`docs/core-v0.1/TECHNICAL-BASELINE.md` separates primary-source findings from live
observations, records both attempts, explains the gate classifications, and names
what remains untested. `TECHNICAL-BASELINE-MANIFEST.json` fixes the specification,
repository, host, Pi, SQLite and DBOS identities and artifact hashes.

The development-only probes live under descriptive `tools/technical_baseline`
paths and are excluded from the installed `zaratustra` package. The published Pi
`0.87.0` process contacted only a localhost HTTP/SSE simulator. The DBOS `3.0.0`
probe used synthetic state in separate `core.sqlite3` and `executor.sqlite3` files.
No provider login, model request, personal data or old workspace participated. The
Pi run's empty isolated auth file and localhost observations do not prove that its
previously inherited ambient environment was never read; the delivered runner now
uses an explicit system allowlist and temporary home that excludes provider secrets.
Direct inspection of the built wheel found no `tools/` or `technical_baseline` entry.

Focused formatting, Ruff, strict mypy and six probe unit tests passed. The complete
`uv run --locked python -m tools.check --deliver` gate also passed: 156 files were
already formatted, Ruff and strict mypy were clean across 134 Python files, all 19
import contracts were kept, all 442 tests passed, and the source and wheel artifacts
built successfully. The required bounded read-only evaluator recheck passed the
complete-check classifier, environment allowlist, descriptive naming and disclosure
fixes; this is a smoke review, not a binding Direction G5 verdict.

## assumptions

Pi remains the provider/model selection and authentication surface; the Core is not
bound to ChatGPT/Codex, Meta Muse, Qwen or a local model. A localhost custom provider
can test the integration seam but cannot prove every real provider transport.

An inconclusive DBOS gate blocks the DBOS-dependent execution stage only. A separately
authorized domain-foundation stage may proceed without choosing a custom dispatcher.

## cuts

No Core v0.1 domain schema, Activity/Work runtime, memory, Sleep, installer, updater,
replacement dispatcher, Pi fork, model router, real model smoke, migration from old
`.zara`, CI/CD, GitHub Action or push automation was added. Pi and DBOS were not added
to `pyproject.toml` or `uv.lock`.

## cost

The change is limited to the authority/baseline documents, exact dependency manifest,
development-only localhost probes and focused tests. Temporary Pi, fixed SQLite and
DBOS runtimes exist only in ignored scratch space in the isolated worktree. No paid
model or external service call was made.

## manual-acceptance

The owner explicitly authorized implementation of Stage 1 and separately clarified
that the product must not be locked to one provider. Automated evidence establishes
only the mechanics listed above; both inconclusive gate decisions and any transition
to Stage 2 remain visible owner decisions.

## next

solmax

END_OF_FILE: RESULT.md
