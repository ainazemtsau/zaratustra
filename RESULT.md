# Concurrent workspace delivery

Base: 4f31e3088a95fdad41457418d4b18963b4c69488. Branch codex/concurrent-workspace.
Package 0.6.0-dev.1. Qualified runtime: Pi 1.4.0, isolated Node 24.22.1 / SQLite 3.53.4.

Delivered: stable SQLite coordination, short complete Core phases, OS runtime leases,
FIFO admission, narrow document/native reservations, cancellation and crash recovery.
Schema 9/control 2 preserve domain IDs, history and materials while fencing old writers.
Live cursors and incremental access/text indexes preserve privacy across concurrent work.
Restore drains live operations, preserves unknown barriers and recovers dead administrators.
No server, daemon, launcher, per-Activity databases or runtime Git was added.

Owner amendment: ten processes are sufficient; no further 100-process/heavy-growth runs.
Accepted synthetic evidence: 2 processes/20 receipts (~1.57s execution), 10 processes/
100 receipts (~9.14s). Seed history and cursor continuation preserved. These are real
storage/Core processes, not model sessions. Two earlier larger failures remain FAILED
in scale-attempt-01.json and scale-attempt-02.json; 100-process support is NOT qualified.
No stress processes remain. Fixtures were Windows Temp directories, never private ZT.

Final focused tests: 51 PASS, zero failures/skips, 48.8s, at most two test suites at once.
Types, source lint, build and module boundaries (44 modules/127 dependencies) passed.
Targeted review found and refuted close/cancel/claim/retry/orphan/drain/restore races;
final reviewer found no important remaining issue in amended 10-process scope.
Neighboring Core/Work/P2: 27 initially passed; two obsolete assertions were updated and
passed individually. Full historical check/deliver was not run. Full R1/T31 and real
owner usefulness are not claimed. Product provider/model calls: ZERO.

Global Node/Pi and private ZT/Health were unchanged. Close old Pi sessions once, update
Node to the qualified 24.22.1, then install the exact published commit locally. Existing
Activities migrate safely; no restart-from-scratch or per-launch variables are needed.
Live owners cannot be displaced by timeout; uncertain actions require inspection, not
replay. One computer/local disk, cooperative trusted agents. Arbitrary shell exactly-once,
independently versioned Work steps and multi-device concurrent work remain separate.
Details: CONCURRENCY.md; evidence: concurrency-evidence/verification.json and scale.json.

END_OF_FILE: RESULT.md
