# SQLite client lifetime — 0.25.1 evidence

## Scope and authority

The owner requested correcting the repeatedly open SQLite issue and explicitly
approved [the idle-client contract](sqlite-client-lifecycle-plan.md). Baseline:
public `193383f`; branch `codex/sqlite-lock-lifecycle`. Product 0.25.1 keeps schema
18. Implementation and checks are complete. Code was published to public
`ainazemtsau/zaratustra/main` as
`d547b886f7c1e38aaef447f72aa0877835249239`. Authenticated GitHub readback and
fetched Git main agree with that commit; production source matches the checked
commit and version 0.25.1. This report update changes no wheel bytes.

Ordinary and assigned Pi use the same BridgeServer resource boundary. Its
Foundation client has a physical rw handle with query_only, completes its checked
initial transaction before yielding and never exposes SQL to callers. It keeps
WAL open during ordinary short operations; current identity/epoch/rights are not
cached. Accepted HTTP handlers drain before client and maintenance fence release.
Inactive socket reads are bounded. No execution queue, service or new authority
is added. SQLite FULL commits, native checkpoint configuration, operation retry
and current Work acceptance rules are unchanged.

## What the investigation establishes

- Saved failure: first process-boundary identity read refused, then tool-result
  capture refused; no draft model invocation had started. Subsequent RPC EOF is
  a later stop outcome, not the original lock cause.
- Audit found no Core transaction held over RPC/network waits or subprocess
  startup. DBOS uses its separate executor database.
- Real SQLite with ordinary WAL configuration: normal last writer close blocked
  the new reader. With 1.081 GiB WAL, close took 3.222 s and all three reads
  received `SQLITE_BUSY`. With an idle client, writer close did not perform the
  final checkpoint; the first read succeeded with unchanged timeout/retries.
- A ro last client left committed WAL pending. The implemented query-only rw
  client was separately proved to leave no transaction/write capability while
  performing SQLite's normal final checkpoint at close.
- Two observer-only installed abort runs did not reproduce the original identity
  error. One observed transient concurrent stop writers and diagnostic I/O
  affected its scheduling. Both retained paused/interrupted/unknown state after
  closure; neither passed its probe observation barrier. They are not PASS.
- The original small-space log lacks the other handle/checkpoint/close timing.
  The concrete mechanism is reproduced; that historical holder remains unknown.

SQLite documents this last-client behavior and first-client recovery locks:
[WAL contention](https://www.sqlite.org/wal.html#sometimes_queries_return_sqlite_busy_in_wal_mode),
[shared-memory lifetime](https://sqlite.org/walformat.html).
Disabling close checkpoint alone was rejected because it moves retained-WAL
validation to first-open; [SQLite author explanation](https://sqlite.org/forum/forumpost/40297ca759).

## Previous probe gap and correction

The existing native harness could finish on Core readiness before the main agent
settled, including a free conversation without selected Work. It also allowed
deadline/unexpected EOF to return by matching HTTP counts. The correction derives
an explicit observed termination fact, resets settlement before every next
prompt/compact and fails incomplete observation. Intentional EOF/abrupt,
catalog, compact and preflight observations retain distinct purposes.

Rejected setup stages do not have a valid stage.output. Their exact raw Artifact
is read through rejection.artifact, without treating it as an accepted proposal.

Two further fixture gaps were corrected without relaxing Core. Intentional
repeated publication failure has no final proof and leaves an ordinary Attempt
active for inspection. The fixture now records that exact state and explicitly
interrupts the stopped native execution through public Core before opening a
different Work. Its Work, invocations, outputs and accounting stay unchanged.

The abort provider held its reply until a committed pause was observed, but the
completion helper waited for the executor to end before making that observation.
An independent fixture poll now observes the pause and releases the withheld
provider. The completion predicate is pure; native settlement, idle coordination
and exact saved stop evidence are still required. Earlier incomplete trials are
not PASS.

## Adjacent defects established and corrected

The corrected abort trial exposed a real split pause. A shared local stop flag
woke the workflow executor while the adapter separately read and stopped the
same assignment. The competing stop could make the adapter request stale and
discard its subsequent pause. Saved native history had a workflow stop but kept
the setup drafting until window closure. The swallowed exception's exact code
was not retained; a public-operation interleaving on the earlier installed wheel
reproduced the same drafting/stop_requested/running result.

Setup and workflow now call their existing atomic Core pause first. That operation
stores process control and current assignment stops together; local teardown
follows in finally. Refusals propagate. Orphan process cleanup retains its old
stop/unknown semantics and cannot invent a successful Work.

Ordinary startup registers native resources with ExitStack immediately when
acquired. All controller cleanups run even if one refuses. Assigned cleanup does
not join unstarted server, stderr or monitor threads. These checks prevent startup
failure from skipping socket/client release and the actual stop record. No new
schema, graph, queue or authority was introduced.

## Actual checks

- Foundation: 50 focused tests passed, types/Ruff/hygiene passed. These include
  independent writer/reader, no snapshot, unchanged rights/receipts/schema18,
  default last-close checkpoint, multi-client closure, verified backup/restore,
  constructor/config/identity/commit failure, caller exception, maintenance
  exclusion/release and real child-process death after its commit barrier.
- One full `uv run --locked python -m tools.check --deliver` passed: 1231 tests in
  1129.51 seconds, build/hygiene/report structure, 315 formatted files, types for
  280 source files and 32 kept module boundaries. This was before the subsequent
  concrete pause/startup corrections; it is not a claim of a second full gate.
- Affected adapter/conversation/probe scope: 119 passed; four actual-HTTP cases
  failed only with sandbox WinError10013. All four passed in their scoped
  localhost repeat. A prior scoped invocation could not create sandbox Temp;
  subsequent probes used verified fresh workspace temporary directories.
- The pause regression fails on the earlier installed wheel and passes after the
  Core-first correction. Genuine revoked rights preserve state and return the
  refusal. Ordinary startup and all three assigned thread-start failure cases
  retain their exact exception, observed child termination, stopped/interrupted
  records, socket closure and maintenance release, without model calls or Work
  acceptance. One close refusal does not skip other controller cleanup.
- Exact final installed wheel: seven selected fault/interleaving tests passed,
  then the separately selected controller-refusal test passed: eight cases total.
  Actual lifecycle assertions precede fixture fallback cleanup.
- Affected Ruff/format/hygiene and mypy checks passed; seven existing native
  observation tests passed after completion/barrier changes.

### Ordinary installed Pi

The complete fictional ordinary-Pi path passed from installed candidate wheel
`0b1b2cb4f6d2cb2df09c4a81344149cd4a2bc8225e199447b4221c4d047c8846`:

- schema 15 to 18 preserves the existing fictional Development inputs/history;
- two successive questions, confusion without answering, closure/new chat/answer;
- two raw-result repairs, whole reviews/correction, usable activation;
- six exact terminal protocol/original/manifest/accounting/order proofs;
- first typed Work, output field diagnostics, compact and exact result reopening;
- later Development structure adoption and continuation of its pre-upgrade Work;
- 54 actual localhost HTTP requests equal 54 accounted deliveries; Work acceptance
  remains absent.

That candidate also passed native abort/reopening with four HTTP requests. Its
assigned outcome was unknown, retained as an obstacle without regeneration.

The only subsequent production delta adds two ident guards for failed startup of
stderr/monitor threads. The final installed wheel repeats their fault cases and
the addressed native abort/reopening path: four HTTP requests, one assigned send,
pause saved before provider release, answered late original and exact visible
terminal proof retained, response recovery available, stopped Attempt remains
interrupted, no activation or acceptance. Actual source/manifests/accounting are
checked. No replacement assigned send occurs.

The child response interruption is not controllable through a supported capture
observer. The preceding unknown and final recoverable outcomes are actual native
observations, not a guarantee of that race's outcome or a patched runtime.

### Final artifact and independent check

Final wheel: `dist/zaratustra-0.25.1-py3-none-any.whl`.

SHA256: `36fb3ea6fa18f7d30507d4bdd24c1dee6863d016d69682d4b5d4d8c9be470fd0`.

The bounded read-only evaluator confirms all 124 production members equal the
wheel, installed package and source; version 0.25.1, schema 18, public managed
client and contract 36/PROBA. Models, operations, runtime, canonical serialization
and schema definitions remain identical to baseline `193383f`. The evaluator used
only two in-memory SQLite import checks, no domain data, tests or provider calls.
Its final affected repeat supersedes earlier candidate smoke hashes.

Independent bounded reviews found the HTTP-drain, completion, split-pause and
startup gaps; the corresponding corrections and their targeted evidence are
recorded above. Fault-test review confirmed actual assertions before fallback
cleanup. No real Pi subscription/paid API calls, private data changes, private
installation, exports or Activity deletion were performed. Code checks and
publication are separate from owner acceptance.
