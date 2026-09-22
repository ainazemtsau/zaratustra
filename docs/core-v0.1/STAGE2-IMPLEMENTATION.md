# Core v0.1 Stage 2 implementation

## Delivered boundary

Stage 2 implements the independent subject foundation in `zaratustra.foundation`.
It neither imports `zaratustra.core` nor reads legacy `.zara` layouts. A new space
uses `.zara-core/core.sqlite3`; initialization accepts only an existing empty
directory and starts with zero subject records and state revision zero.

The supported runtime is Python `3.13.7` with exact SQLite `3.53.3` and FTS5. The
foundation fails at import before opening a space when another SQLite build is
loaded. On Windows the verified official DLL is supplied per process through
`ZARATUSTRA_SQLITE_DLL`. Exact identities:

- archive: `sqlite-dll-win-x64-3530300.zip`;
- archive SHA3-256:
  `3a494861ce24d1f330efbc6c3fb58ce4972f2cf8df4e43122246ed987109dc8a`;
- extracted `sqlite3.dll` SHA-256:
  `79FD9EC89DBA3F8BD64529A2CA8E9DDE6AE6EDC486C55A1D3F1CE77975A8375C`.

The archive identity comes from the Stage 1 manifest; the extracted DLL hash is
checked by product runtime admission before `ctypes.WinDLL` loads it. The repository
does not vendor or silently download this binary and does not change the global
Python/SQLite installation.

## Actual operations

| Request | Effect | Current required condition |
|---|---|---|
| `BootstrapRequest` | atomically creates the root require-Grant Decision and root space Grant | new empty active space plus trusted-local authority |
| `CreateArtifactRequest` | creates Artifact revision 1 and exact managed bytes/provenance | `artifact.write` Grant; no applicable deny Decision |
| `ReviseArtifactRequest` | appends one immutable revision and advances current | exact current revision plus the same current admission |
| `DeleteArtifactRequest` | blocks every revision read, removes managed payload/provenance, redacts payload-derived receipts/fingerprints and opens cleanup | exact current revision plus `artifact.write` |
| `CreateDecisionRequest` | creates a typed `require_grant` or `deny` Decision | `decision.write` |
| `ReviseDecisionRequest` | appends a Decision revision, including explicit revocation | exact current revision plus `decision.write` |
| `CreateGrantRequest` | creates a space- or Artifact-scoped Grant in the current execution epoch | `grant.write` |
| `RevokeGrantRequest` | appends a revoked Grant revision | exact current revision plus `grant.write` |
| `RecoverRequest` | establishes fresh root Decision/Grant and leaves quarantine in a rotated epoch | fresh non-backed-up recovery authority |

Every request includes protocol version, space and operation identity, actor,
operation-specific intent and all required expected revisions. Canonical JSON plus
SHA-256 defines exact identity. One `BEGIN IMMEDIATE` transaction changes records,
immutable revisions, operation audit and receipt together. Exact replay returns the
saved receipt; changed intent under the same id conflicts. A receipt removed with
managed content returns `history_unavailable` rather than reconstructing or replaying
the old intent.

Trusted adapter values contain the real local source reference and are bound to the
resolved space path, space id and execution epoch. Request fields such as `actor` do
not create authority. Mutation, record-read, receipt-read, inspection, backup and
deletion rights are distinct actions. Active Decision denies are evaluated from the
current revisions inside the same transaction as the change.

## Storage and inspection

The initial strict schema contains:

- space/schema identity, state revision, execution epoch and recovery state;
- typed records and immutable revisions;
- one managed payload table and explicit internal/external provenance;
- operations, payload-free audit references and receipts;
- deletion jobs plus managed backup/record inventory;
- maintenance events.

Writers use WAL, `synchronous=FULL`, foreign keys and `secure_delete=ON`. Begin uses a
250 ms SQLite busy timeout with at most three bounded attempts. All product
connections use explicit `closing`/`finally`; model/network/long tool work has no
place inside these transactions.

The public model-free inspection reads bounded metadata, current or exact historical
Artifact bytes, and separately authorized receipts. An absent/deleted exact revision
never falls forward to current content. Quarantine inspection exposes only space,
schema, state and epoch metadata.

## Backup, restore and deletion boundary

`create_backup` uses the SQLite Backup API and writes `manifest.json` last before the
package directory becomes visible. The manifest binds space, schema, state boundary,
execution epoch, database filename and SHA-256. Completed packages live under the
space's managed backup directory and their contained Artifact ids are inventoried.

Restore verifies manifest/hash/database agreement and accepts only a new empty
destination. It rotates the execution epoch and opens in `quarantined`; backed-up
Grants therefore do not authorize reads or mutations. A fresh trusted-local
`RecoverRequest` creates new epoch-bound roots before normal access resumes.

Artifact deletion commits an immediate logical gate and removes managed payload and
provenance from ordinary tables. `complete_deletions` removes every affected managed
backup package, clears its retained database digest, closes product handles,
checkpoints/truncates WAL, runs `VACUUM` under `secure_delete=ON`, records completion
and checkpoints again. Audit retains permitted identities/outcome references but no
payload, payload digest or recoverable receipt intent.

The claim is limited to files managed by this stage: the live core database and its
WAL/SHM plus registered completed backup packages. SSD remapping, OS snapshots,
unregistered copies and external systems are outside it and are not called erased.

## Reproduction without a model

Use a new ignored output directory and the verified DLL extracted from the exact
archive above:

```powershell
uv sync --locked
uv run --locked python -m tools.probe_foundation `
  --sqlite-dll <path-to-verified-sqlite3.dll> `
  --output _scratch/<new-directory>
```

The probe uses only public foundation calls and synthetic values. It creates and
reopens a space, bootstraps authority, writes text and binary revisions with
provenance, proves exact replay and receipt recovery, creates a verified backup,
restores it in quarantine, recovers under a new epoch and checks exact restored bytes.
It writes `summary.json` in the selected scratch directory.

## Checks and remaining limits

Focused automated coverage includes create/reopen, no legacy import, unsupported
schema/runtime refusal, exact text/binary revisions, provenance, replay/conflict,
stale revision, separate receipt-read, Grant revocation, Decision denial/revocation,
rollback at the receipt seam, lost-response recovery, concurrent stale update,
concurrent exact duplicate, backup tamper refusal, quarantine/fresh recovery and
closed-store deletion from live SQLite/WAL and managed backups.

This stage deliberately has no Activity/Work runtime, Attempts, scheduler,
dispatcher, outbox, Pi integration, DBOS dependency, memory, Sleep or developer
workflow. DBOS remains an open technical question: before connecting it, obtain
stable Windows evidence that all relevant handles close and managed technical payload
can be removed. Do not narrow the deletion guarantee silently and do not select a
custom dispatcher automatically.

END_OF_FILE
