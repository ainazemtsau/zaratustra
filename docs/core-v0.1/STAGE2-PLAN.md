# Core v0.1 Stage 2 — independent domain foundation

## Authority and boundary

The owner authorized Stage 2 on September 22, 2026 from exact commit
`7ec6033d234b0e2e870f53796a9dad0711d3b468`. The governing specification is
`Zaratustra_Core_Specification_v0.1.md`, SHA-256
`1DDCBF9DBFD58426781F61A67A170D3CE85FCD2BA27B17549773ED3356F9428D`.

This stage implements only the specification's "Общая предметная основа" group and
the directly required AD02/AD07 contracts: the minimal persisted-object roles,
Decision and Grant, invariants, the single-operation/replay contract, revisions and
current grounds, SQLite state, deletion, backup/restore, external inspection and the
corresponding proportional engineering checks. Stage 1 remains historical evidence.

Pi and DBOS are not production dependencies. Scheduler/dispatcher, Attempts, Work
execution, Activity creation, memory, Sleep, model integration and developer
workflows are not implemented or stubbed. DBOS-dependent execution remains blocked
until deterministic closed-handle sanitation of managed technical payload is shown.

## Supported product surface

The new `zaratustra.foundation` package is independent of legacy
`zaratustra.core`. Its public, model-free Python surface supports:

1. create and reopen a new empty space at `.zara-core/core.sqlite3`;
2. establish or recover a trusted-local root Decision and Grant;
3. create/revise a typed Artifact with exact managed text or bytes and explicit
   internal/external provenance links;
4. create/revise a typed Decision whose active deny conditions constrain later
   operations but never grant authority;
5. create/revoke a typed Grant for separate mutation, record-read, receipt-read,
   inspection and maintenance actions;
6. apply every domain change through one structured operation envelope with protocol
   version, space/operation identity, actor, operation-specific intent, exact expected
   revisions and a canonical SHA-256 fingerprint;
7. read the current or one exact historical Artifact revision, an operation receipt,
   and bounded space/record/revision inspection under current rights;
8. create a SQLite Backup API package, verify and restore it only into a new
   quarantined space, and recover it under a fresh trusted-local epoch;
9. logically delete every managed payload revision of one Artifact, block reads
   immediately, purge affected managed backup packages, checkpoint/VACUUM the live
   store and report whether physical sanitation is complete.

Exact replay returns the prior receipt without a second effect. A changed request
under the same operation id, a stale revision, a current Grant/Decision refusal,
unsupported schema/runtime and an exhausted busy retry return distinct failures.
Receipt disclosure is authorized separately from mutation execution.

## Schema and durability

One authoritative database stores space/schema identity, a global state sequence,
execution epoch/recovery state, records and immutable revisions, managed payload,
provenance, operations, audit references, receipts, deletion jobs and managed backup
inventory. Audit and receipts contain identifiers and structured outcome metadata,
never a second copy of managed payload. Current records are projections over retained
revisions; historical reads never fall forward to the latest revision.

The only supported Stage 2 runtime is Python `3.13.7` with SQLite `3.53.3`, FTS5
available, WAL, `synchronous=FULL`, foreign keys, `secure_delete=ON`, a 250 ms
SQLite busy timeout and at most three bounded begin attempts. On Windows the already verified official
`sqlite3.dll` is loaded per process before `sqlite3`; its SHA-256 is
`79FD9EC89DBA3F8BD64529A2CA8E9DDE6AE6EDC486C55A1D3F1CE77975A8375C` and the
source archive identity remains in `TECHNICAL-BASELINE-MANIFEST.json`. Other SQLite
versions fail explicitly rather than silently changing the durability contract.

Initialization requires an existing empty directory and never scans, imports or
changes legacy `.zara` spaces. Unknown application/schema identities fail without
creating a replacement database or running a migration.

## Module boundaries and reuse

- `runtime.py`: exact SQLite runtime admission before the stdlib binding loads.
- `models.py`: frozen request, record, receipt and inspection contracts.
- `storage.py`: layout, schema, checked connections, exact reads and maintenance.
- `operations.py`: the sole post-initialization domain mutation path and current
  Decision/Grant evaluation.
- `__init__.py`: the complete public surface.
- `tools.probe_foundation`: a synthetic, reproducible, model-free usage example.

Reuse is limited to the repository's proven small patterns: Pydantic v2 immutable
models, canonical JSON/SHA-256, short `BEGIN IMMEDIATE` transactions, explicit
connection closing and the existing PROBA/import-linter/test harness. Legacy schema
1–9, migrations, portable writer and trusted adapters are not imported.

## Verification

Focused tests cover empty create/reopen, exact text/binary revisions and provenance,
exact replay/changed intent, stale revisions, revoked/denied rights, rollback on an
injected receipt-write failure, receipt recovery after a discarded response,
same-record and duplicate-operation concurrency, unknown schema/runtime refusal,
backup verification/quarantined restore/fresh recovery, deletion read blocking and
closed-store removal from DB/WAL/managed backups. The model-free probe exercises the
public contract on synthetic data. Final evidence is the full
`uv run --locked python -m tools.check --deliver` run in the supported runtime.

## Known boundary after this stage

Deletion covers payload managed by this stage: the live core database, its WAL/SHM,
and completed backup packages recorded in its inventory. It does not claim physical
erasure from SSD remapping, OS snapshots, unregistered copies or external systems.
Restore is intentionally quarantined and does not reactivate backed-up Grants. No
executor database exists in this stage. Before DBOS is connected, obtain stable
evidence that all DBOS/SQLite handles close and managed technical payload can be
removed on Windows; do not silently narrow that guarantee or select a custom
dispatcher.

END_OF_FILE
