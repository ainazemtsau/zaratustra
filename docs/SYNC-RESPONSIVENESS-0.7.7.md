# Responsive checkpoint preparation — 0.7.7

Automatic Git preparation ran synchronous filesystem scans, repeated full raw-byte
checks and a blocking native Git hash process on the same JavaScript thread as Pi's
terminal. A checkpoint outside the memory gate could therefore still freeze input
and drawing. Gate separation alone did not establish UI responsiveness.

Preparation and byte verification now yield to actual event-loop macrotasks between
bounded batches. The batched native content-hash process runs asynchronously with
stdin and bounded output. Short coherent admission and staging callbacks remain
synchronous; no model, network operation or new background service is introduced.

The correction preserves raw hash validation, exact canonical membership, portable
attributes, owner staging, exact index/commit trees, HEAD/branch/parent checks,
remote identity, outgoing blob limits, request handling and epoch fencing. Yielding
allows ordinary work to progress; changed inputs still require recapture or leave
the exact older checkpoint with newer changes explicitly pending.

Memory format, schema, control protocol and application data are unchanged.
No model or paid API conversation is required for this correction.

Validation: seven focused checkpoint scenarios passed, including a 2,048-file
heartbeat case, timer-driven late edit, portable canonical bytes, exact inventory,
admission gates and concurrent changes. One subprocess-control test passed four
cases: exact multi-MiB UTF-8 stdin, early exit/pipe error, timeout termination and
already-aborted startup. Types, targeted ESLint/formatting, dependency boundaries
and build passed. Read-only source review found no blocking issue.

This is not a strict latency guarantee: synchronous short preflight/admission/Git
commit work remains, and one slow filesystem operation can exceed a batch target.
No timeouts or integrity checks were relaxed, and no owner corpus is included in
public fixtures. An already running Pi must /reload to use the updated code.
