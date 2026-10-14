# SQLite client lifetime — approved correction

## Authority and current status

The owner explicitly requested investigation and correction of the repeated
SQLite blocking observation. Current public baseline is `193383f`, product
0.25.0, schema 18. Branch: `codex/sqlite-lock-lifecycle`.

The owner explicitly approved implementing and checking this runtime
resource-lifetime contract. Implementation and checks are complete locally;
publication is pending. No private installation or data operation has been
performed. The independent probe's completion/barrier gaps and the adjacent
pause/startup defects are corrected; exact evidence is in the 0.25.1 report.

## What is proved

1. In the saved ordinary-Pi failure, `/v1/process-boundary` first refused
   `application_id / SQLITE_BUSY`; then `message_end` capture failed. The
   assigned draft had no provider invocation. Its subsequent RPC EOF is not
   the first failure.
2. Adapter/Core audit found no SQLite transaction retained over network, RPC
   waits or subprocess startup. Nested setup effects reuse the transaction's
   existing connection. DBOS uses a separate executor database.
3. Core normally opens and closes a connection for each public call. Foreground
   observation, assigned control and UI status produce concurrent short clients.
4. Real Windows SQLite 3.53.3 reproduces a normal last-client-close checkpoint
   blocking a new first identity read. With a 1 GiB fictional WAL it exceeded
   all three existing read retries. The same connection subsequently succeeded;
   neither reconnect nor changing ro to rw is a correction of that mechanism.
5. The historical small-space log did not identify its other live handle or
   checkpoint. The large-WAL reproduction proves a mechanism and inadequate
   lifetime policy, not the exact historical holder.
6. Two observer-only native runs did not reproduce the historical first-read
   failure. One saw temporary contention between workflow/setup stop writers;
   its diagnostic I/O affected scheduling. Both retained truthful paused and
   interrupted state after closure. Neither passed its observation barrier.
7. A new uninstrumented installed setup reached ready with all six assigned
   originals/accounting retained. Its probe terminated before the main agent's
   final request: queue-empty polling accepted Core readiness without native
   `agent_settled`. The local harness correction requires both conditions,
   including a free conversation without selected Work.

Official SQLite describes last-client cleanup and first-client recovery locks:
[WAL contention](https://www.sqlite.org/wal.html#sometimes_queries_return_sqlite_busy_in_wal_mode),
[WAL shared-memory lifetime](https://sqlite.org/walformat.html).

## Rejected changes

- No increasing arbitrary retries/timeouts or replaying an operation body,
  commit or model send.
- No new queue, daemon, backend or text filter.
- No claiming that a successful repeat identifies the previous holder.
- No disabling close checkpoint as a complete solution. The stock
  `SQLITE_DBCONFIG_NO_CKPT_ON_CLOSE` setting is durable with FULL commits, but
  retained WAL must be revalidated by the next first client and can move
  contention to that boundary. It is not selected for this correction.
- No exclusive locking, live `immutable=1`, removing WAL files, weakening
  identity checks or changing rights/receipts.

## Approved client lifetime

Give the existing ordinary/assigned Pi bridge a checked, idle Core client for
its actual host lifetime. Ordinary public operations continue using their
existing short transactions. The idle client has no active transaction, does
not hold a snapshot or write lock and cannot issue domain operations.

The physical handle is opened rw with `query_only=ON`, not mode=ro. A last ro
handle does not perform SQLite's final writable checkpoint; the real feasibility
comparison found committed data left in WAL. Query-only admission forbids SQL
mutations while allowing the owning runtime's normal final close/checkpoint.
The connection is never exposed to callers and does not grant record rights.

- Public Foundation context manager owns opening, identity validation,
  completed initial read transaction and unconditional close.
- Scope uses the existing managed Pi session/maintenance fence; no extra
  persistent state or Core schema is added.
- Ordinary and assigned hosts acquire it before accepting bridge requests and
  keep it until execution/HTTP cleanup ends.
- The actual bridge-server resource boundary owns the scope so the normal
  installed Pi and its native harness use the same behavior.
- Constructor/configuration/startup failure closes the SQLite handle and socket
  and releases the existing maintenance fence.
- Close is idempotent and occurs on its owning host thread. It cannot suppress
  a Core failure, acknowledge a model send or accept Work.
- Existing native checkpoints, synchronous FULL commits, WAL configuration,
  explicit sanitation/backup and authorization remain unchanged.

This prevents ordinary per-call closes from becoming the last WAL client while
Pi is running. It does not invent evidence for a historical uncorrelated failure.
First startup, final shutdown, crash and immediate reopening must be checked
separately; an external exclusive holder still produces an honest obstacle.
If feasibility shows another ownership contract is needed, stop for owner
discussion rather than adding a second coordination lock.

## Stop and startup corrections exposed by this verification

The native abort check exposed a separate split stop: the adapter set its shared
stop flag, requested an assignment stop from a snapshot, then intended to save
the Activity pause. The workflow executor could stop the same assignment first.
The adapter's refusal discarded the remaining pause. A public-operation
interleaving reproduced `drafting` plus `stop_requested` on the earlier wheel.

The existing Core setup/workflow pause already stores process control and all
current assignment stops atomically. Use that operation first, signal local
teardown afterwards and preserve any refusal. Drain owned resources even when
one close refuses. This adds no schema, execution graph or domain authority.

Ordinary startup registers native cleanup on acquisition with ExitStack.
Assigned cleanup joins only actually started server, stderr and monitor threads;
an unstarted join cannot skip socket/client closure or the observed stop record.
These are checked startup boundaries of the approved client lifetime.

The fictional abort provider's release barrier must be observed independently of
the completion predicate. An executor cannot be required to finish before its
withheld provider is released. Completion still requires native settlement,
idle coordination and the exact saved pause/stop evidence.

## Checks before any delivery claim

Use real SQLite and existing public operations with fictional material:

1. Natural close/read reproduction with an idle client: reader sees committed
   identity/data without a close-time checkpoint. After all clients close, the
   default checkpoint remains functional.
2. Idle client has no transaction and does not block another writer or current
   reads. Repeated calls retain exact record revisions/receipts.
3. Two clients, close one, stop/open another, final close and process death:
   locks are released, restart reads the exact committed state.
4. Existing maintenance excludes a live client, succeeds after close; verified
   backup/restore and deletion still cover all managed state and WAL bytes.
5. Constructor/configuration/HTTP bind failures and repeated close leave no
   database/socket/fence leak.
6. Ordinary wheel-installed Pi: create, whole draft/review/correction, visible
   final, first Work, close/reopen and exact Development continuation. Assert
   actual native settlement and actual HTTP/ContextManifest/accounting, not
   only Core readiness.
7. Native abort/late reply: saved pause/unknown response remains truthful,
   no replacement request or automatic acceptance.

Expand relevant existing tests, then one full native gate on the completed
package and only affected repeats. One bounded read-only evaluator verifies
the installed wheel. No real provider/subscription calls are authorized by
this package. Preserve untracked parallel work and all personal Activity/data.

Delivery, if approved and verified: patch release 0.25.1, schema 18 unchanged,
public `ainazemtsau/zaratustra/main` only. Record exact historical-evidence limits
and actual native results separately from owner acceptance.
