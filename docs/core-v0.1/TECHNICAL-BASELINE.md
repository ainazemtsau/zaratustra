# Core v0.1 technical baseline

## Decision

Stage 1 is complete with two **inconclusive** gates. The completed observations
are useful, but neither upstream Pi `0.87.0` nor DBOS `3.0.0` is admitted as a
production dependency by this result.

This does not select a provider, a model, a Pi fork, or a custom runner. Pi remains
the proposed provider/model selection and authentication surface. ChatGPT/Codex,
Meta Muse, Qwen, a local model, and a custom provider are architectural choices at
that boundary rather than separate Core implementations. The probe deliberately
used only a localhost custom provider and therefore makes no claim that every real
provider uses an identical transport.

Stage 2, when separately authorized, may build the independent domain foundation
without DBOS. DBOS-dependent Stage 4 remains blocked pending a new, narrowly scoped
decision. There is no automatic fallback to an in-house dispatcher or Pi fork.

## Scope and isolation

The tracked probe lives under `tools/technical_baseline`. It is development-only,
is not included in the installed `zaratustra` package, owns no product state, and
does not use numbered specification clauses in source file names. `G07-1` and
`G08-1` occur only as traceability labels in evidence and this report.

All runtime state is below ignored `_scratch` directories in the isolated worktree.
The controller did not inspect credentials, log into a provider, send a model request,
alter global npm, modify an old `.zara` workspace, or add Pi/DBOS to `pyproject.toml`
or `uv.lock`. The historical Pi runs did inherit the ambient process environment;
although the isolated `auth.json` was empty and the observed provider traffic was
localhost-only, those runs cannot prove that Pi never read a credential variable.
The delivered runner fixes this by passing a small Windows system allowlist and a
fresh temporary home, explicitly excluding provider credentials.

The exact environment and artifact identities are recorded in
`TECHNICAL-BASELINE-MANIFEST.json`. The execution baseline was Windows
`10.0.26200`, PowerShell `7.6.3`, Python `3.13.7`, Node `22.19.0`, uv `0.8.22`,
Git `2.50.1.windows.1`, SQLite `3.53.3` with FTS5, Pi `0.87.0`, and DBOS `3.0.0`.

## Static primary-source findings

These are documentation/source-reading results, not claims that the behavior was
exercised end to end:

- SQLite WAL permits only one writer at a time, requires all participants to share
  the same host, and cannot be safely snapshotted by copying an open database file.
  SQLite's WAL-reset defect is fixed in `3.51.3` and later and in backports `3.50.7`
  and `3.44.6`. Sources: [WAL](https://www.sqlite.org/wal.html) and
  [Backup API](https://www.sqlite.org/backup.html).
- DBOS documents SQLite as a local prototyping/testing system database and requires
  Postgres for a distributed multi-server setting. Queues and workflow state live in
  the DBOS system database. Sources: [database connections](https://docs.dbos.dev/python/tutorials/database-connection),
  [queues](https://docs.dbos.dev/python/tutorials/queue-tutorial), and
  [3.0.0 release](https://github.com/dbos-inc/dbos-transact-py/releases/tag/3.0.0).
- Pi `0.87.0` declares Node `>=22.19.0`, exposes an RPC entry point, and documents
  subscription, API-key, local and custom provider paths. The documented provider
  list includes ChatGPT/Codex and Meta Muse; custom/local paths cover Qwen-like and
  local servers without making them Core-specific. Sources: [package](https://github.com/earendil-works/pi/blob/v0.87.0/packages/coding-agent/package.json),
  [RPC](https://github.com/earendil-works/pi/blob/v0.87.0/packages/coding-agent/docs/rpc.md),
  and [providers](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/providers.md).

Static inspection of the installed DBOS `3.0.0` SQLite backend found
`isolation_level="IMMEDIATE"`, `busy_timeout=30000`, and `foreign_keys=ON`; it did
not find DBOS enabling WAL. Reading the databases produced by the probe confirmed
`core.sqlite3` in WAL mode and `executor.sqlite3` in DELETE journal mode.

## Pi integration gate (G08-1)

### Executed evidence

The published npm artifact ran as a real Pi JSONL RPC process against a localhost
HTTP/SSE provider simulator and a small Pi extension. Startup network, telemetry,
agent retry, provider retry and cache warming were disabled. The already executed
runs nevertheless inherited ambient environment variables as disclosed above; the
delivered allowlisted environment was not used to claim new live evidence.

Observed successfully:

1. The exact serialized request body sent to localhost matched the digest persisted
   by the extension. SHA-256:
   `9ae71ded99d97b35cad9a166b9be1ff0fb51a01f87cf21eaa6a3f2839ddfc965`.
2. A forced failure of the required pre-send observation caused zero additional HTTP
   requests.
3. JSONL framing was LF-based; U+2028 inside a JSON string did not split a frame.
4. A question appeared while Pi was streaming without starting another model turn.
   A duplicate UI response produced one continuation.
5. The synthetic durable wait survived termination of the Pi RPC process and was
   redisplayed by a new Pi process.

Not established:

- The synthetic session was too small for manual compaction; Pi returned that there
  was nothing to compact and no summary request was emitted.
- The simulated `context_length_exceeded` response produced a context-edit event but
  not a summary/retry sequence. The probe therefore did not establish distinct
  identities and reservations for overflow, summary and retry.
- No real ChatGPT/Codex, Muse, Qwen or local-model authentication or transport was
  exercised.

The second and final permitted live run wrote a raw result that used the probe's
original binary classifier and therefore said `negative` whenever any check was
false. That classification did not match the approved gate semantics: the required
request/readiness/UI safety observations passed, while compaction coverage was
insufficient. The delivered classifier now distinguishes a conclusive safety failure
from missing coverage. The reviewed gate result is **inconclusive**. No third live
run was made.

Raw evidence is retained locally at `_scratch/g08-run-20260922-a` and
`_scratch/g08-run-20260922-b`. Before the descriptive rename, the executed command
used the earlier module path. The current reproducible entry point is:

```text
python -m tools.technical_baseline.pi_integration_probe --node <node.exe> --pi-cli <pi-cli.js> --package-integrity <integrity> --output _scratch/<new-directory>
```

## Durable execution gate (G07-1)

### Executed evidence

The probe used separate `core.sqlite3` and `executor.sqlite3` files, two subprocess
executors, synthetic identifiers, and no external effect or service.

The following scenarios completed in both live attempts:

1. Process death before the domain commit exposed no partial receipt; DBOS startup
   recovery ran the pending workflow and produced one application.
2. Process death after the domain commit but before the workflow response caused
   DBOS replay; the domain receipt kept the mutation at one application.
3. Repeated enqueue with a stable workflow ID delivered the committed outbox event
   once.

The first attempt reached a DBOS `PENDING` durable wait and created the corresponding
domain wait row, but the orchestration process ended before it captured a report. In
the single permitted targeted repeat, initialization of a fresh DBOS system database
was still applying its 33 shipped migrations when the bounded 15-second readiness
timer expired. The improved harness preserved this stderr instead of leaking the
child process. Its final source uses a 45-second setup bound and writes an
`inconclusive` machine report on bounded timeout, but that correction was not used to
claim additional live evidence.

Consequently scenarios 4–10 were not completed as one bounded run: durable
wait/duplicate answer, stale epoch, current Grant after replay, lost external-effect
reply, unknown outcome with retained reserve, managed payload deletion, and code
version routing remain unproven together. The gate result is **inconclusive**, not a
DBOS rejection. No third live run was made.

The evidence does show that DBOS supplied real checkpoint/startup recovery and a
durable queue in scenarios 1–3. Receipts, outbox, fencing, current-right checks,
resource reservations and unknown-effect policy are intentionally domain fixture
responsibilities. This partial run is insufficient to decide whether the total glue
remains proportionate.

Raw evidence is retained locally at `_scratch/g07-run-20260922-a` and
`_scratch/g07-run-20260922-b`. Before the descriptive rename, the executed command
used the earlier module path. The current reproducible entry point is:

```text
fixed-python -m tools.technical_baseline.durable_execution_probe --output _scratch/<new-directory>
```

## Reproduction and stop

The isolated runtime was prepared with an official fixed SQLite DLL and exact package
artifacts; the user's broken global npm shim was bypassed with npm's installed CLI and
was not repaired. Raw runtime installations and evidence remain ignored scratch data.

This report is the Stage 1 stopping point. Do not create the Core v0.1 domain schema,
add Pi/DBOS as production dependencies, implement a replacement dispatcher, or run a
real provider smoke without a separately authorized transition.

END_OF_FILE
