# E3 read-only preflight -- 2026-10-21

This is planning evidence only. No E3 implementation, executed test, independent verdict,
E2 acceptance, owner-use/T31, full R1, or Direction closure is asserted.

## Authority and observed base

The owner limits this phase to read-only inspection, with this one small note permitted
only inside a previously absent evidence root. E2 remains the sole product writer.
No product/test/Git/install/evidence mutation, model dispatch, credential read, ledger
creation, child agent or chat was performed. Git commands were read-only with optional
locks disabled. The evidence root was absent at initial inspection and immediately
before exclusive creation. No prior evidence was used as a working directory.

Read completely: repository AGENTS and module AGENTS, the public specification including
appendices A-D, DEVELOPMENT, R1-STATUS, RESULT, E2-DESIGN and current E2-ATTEMPTS.
Inspected actual storage, Core contracts/access/commit/snapshot/material reading,
approvals, effects, memory/history/index surfaces, extension import/native confirmation
and store-open paths, and relevant test/source declarations. No tests were executed.
E2-VALIDATION.md and E2-REPRODUCE.md are absent in this observed checkout; current
qualification documents explicitly remain in progress. They must be read after handoff.
The designated reviewer root was only inventoried; no final review verdict was observed.

Specification original SHA256 matched
7d3bd88d71dd954949ad33caae38859f9e06c460b8537ed3259780d11668fac4.
Public derivative was read completely and matched
4940e16e39174df941da98889c43b713c48287d4aeda8754fd57660d462a77cb.

## Concrete gaps and contract tensions

- src/core/index.ts:529 and approval.ts:122 compare context against cached workspace.
  tests/effects.test.ts:1020 changes both cached epochs; it does not prove authoritative
  control rejection of an old async callback after a physical generation switch.
- src/extension/index.ts:136,180,213,523 makes current Core the admission path. A failed
  DB open leaves no Core. Recovery preview/confirmation must work without opening or
  replacing the lost DB and without requiring an old receipt or transcript.
- src/storage/index.ts:351 has a migration VACUUM INTO snapshot, not product backup.
  StoragePort only exposes UTF-8 readMaterial (contracts.ts:686; storage/index.ts:716).
  Binary PDF/EPUB backup needs verified raw immutable bytes and a completed-snapshot
  manifest, never a late live query or arbitrary source_locator copying.
- importMaterial retains original/derivative before c.capture returns a transient source
  (storage/index.ts:680; extension/index.ts:960). Pending source material is not orphan.
- RecordRow.storage is currently only live (contracts.ts:593). Normal snapshot has no
  archive exclusion yet (core/index.ts:1291). Historical reads, addressed_versions,
  FTS, full prepared payloads, preview before-values, managed-file arguments/final_text
  and method_snapshot are potential copies; setting only current body=null is insufficient.
- Preserving DB history and forbidding runnable restored authority are compatible:
  retain historical claims/approvals as facts, invalidate their execution under the new
  external control epoch. Do not silently strip history from a full snapshot.
- Exact approval currently persists in DB intents. Reuse its binding/presentation logic
  for the unavailable-DB recovery case using bounded quarantine/control metadata, not
  another workflow/recovery database or an empty replacement memory.
- Default scopes remain unchanged. Fixed full-read/full-write administrative policy is
  checked before bundle inspection, counts or copying, independent of actual hidden rows.
  Existing per-row filtering cannot make an entire DB snapshot safe for a low-scope caller.

These are E3 extension obligations, not independent findings of failure in accepted E2.
Current in-progress docs and observed candidate are not an accepted final base.

## Implementation and verification order after accepted gate

1. Reread root-owned gate: status=accepted, product_writes_E3_allowed=true, exact
   artifact_sha present. Freshly read final HEAD/status/delta, actual independent final
   review, instructions and final E2 design/validation/reproduce. Verify exact accepted
   base and completed sole-writer handoff before product edits; preserve others' changes.
2. Add the smallest storage/control migration: stable control root and writer lock,
   verified generation directories and atomic active pointer, external epoch/barrier.
   Keep filled E2 canonical/history/support/material data intact during migration.
   Authorize against authoritative active control at admission and after async waits,
   including native dispatch, callbacks and approvals. Preserve old generations.
3. Use installed node:sqlite backup under a short administrative mutation/import/GC gate,
   with no SQL transaction across its await. Derive sequence, exact retained versions,
   grounds and blob set solely from the finished snapshot. Pin before resuming GC;
   independently copy and disk-verify blobs, manifest and versioned JSON export.
   Full-read scope denial precedes source inspection; missing/corrupt material is refusal
   or explicit incomplete artifact. No credentials or runnable restored authority.
4. Quarantine restore validates schema/integrity/FKs/domain refs/versions/materials,
   rebuilds search and obtains the exact E2-style bound decision on identity/destination/
   coverage/loss/switch. The same protocol handles healthy and missing/corrupt DBs.
   Stop conflicting execution; record new epoch and barrier before writable continuation.
   Faults leave verified old active state or read-only/quarantine, never writable partial.
5. Reconcile every restored potentially effectful Work/step, independent of receipt
   presence. Named current observations plus fresh guards/authority clear only that
   action; matching bytes do not identify their writer. Keep unknown/risky repeat honest.
   Allow read-only recovery and demonstrably independent new work.
6. Add archive cards and minimal tombstone schema, explicit retained-version/body-copy
   deletion coverage, reverse-ref refusal with addressed pin reasons, library pins,
   index/snapshot/export invalidation and access protection on every technical surface.
   Preserve receipt identity/hash metadata without exposing deleted payload bodies.
   GC respects history, pending handles/staging, shared blobs, backup-copy pins and
   explicitly held bundles. Check resolved path containment/identity before deletion.
7. Execute disk M faults/negatives and affected B/C/D/E1/E2 regressions, then exact
   installed filled-E2 upgrade/old-writer/fault checks. Freeze/publicly install candidate.
   L: ordinary backup/restore approval/loss explanation; fresh no-transcript A-before-
   intent, B-real-file-write, lost-DB restore and readback before repeat; known-receipt/
   unknown recovery; archive discovery and precise pinned-delete refusal or execution.
   Keep one non-reset E3 ledger only when real checks begin: 30 conversations,
   240 actual provider dispatches, USD20 Pi estimate; fixed gpt-6.1-sol medium/native auth.
   Keep all failed attempts. Run check/deliver, prove final runtime/instruction/test byte
   identity or repeat affected checks in the same budget. Deliver RESULT, E3-DESIGN,
   VALIDATION, REPRODUCE, ATTEMPTS, per-row M/L limits, chat demo, exact public/installed
   refs and external FINAL-READBACK.json. No independent PASS, T31 or full R1 claim.

No ledger, package installation, test workspace, output fixture or model run exists from
this preflight. Stop while gate is pending; resume this same physical session only after
root supplies the accepted exact artifact. F, Codex and Sleep remain outside E3.
next: solmax

Observed HEAD: 0d6c9a2d604aec0f8b108841219c68369189315b
Observed worktree status: ?? docs/e2-evidence/

Gate immediately before note creation:
```json
{
  "status": "pending-independent-final-PASS",
  "artifact_sha": null,
  "code_candidate_sha": "0d6c9a2d604aec0f8b108841219c68369189315b",
  "review_root": "<PRODUCT_CHECKOUT>-e2-independent-0d6c9a2d-20261020",
  "product_writes_E3_allowed": false,
  "actual_owner_T31": false,
  "note": "Only root may accept after substantive independent exact-final PASS and completed sole E2 writer. E3 preflight read-only until then."
}
```

Observed file hashes (mutable E2 preflight observation, not a final frozen artifact):
- AGENTS.md: aa6c18e2e7a52c672d147ae2ef0d0dfac021719152765d7841ba1399866dd6ae
- docs/specification-v1.1.html: 4940e16e39174df941da98889c43b713c48287d4aeda8754fd57660d462a77cb
- docs/DEVELOPMENT.md: 82509314cb8b8ed010643be170675f631cd0ebb8f5664d811cca651de463ee0c
- docs/R1-STATUS.md: 25ff6fac692fdcf0de039361c93a111c3a570026eb7ea21faf4a0552d60ac023
- RESULT.md: 0163600a25ae20e2659ca0e9d267e76b0bcdb4b3a58b9bdd0b4e077876e3098b
- docs/E2-DESIGN.md: e895862ceae680465af418542f758385f0de37fcc6cc36bffd7c95188e4d4d5a
- docs/E2-ATTEMPTS.md: b3db97c5cae2e611bb823c9522d5a807ac1049ef60bc93ebd9b867cc4283aca7
- src/storage/index.ts: 4bf262cc4ddd1f2f3b1d01defe98f83ba96a22b89384b90eb85267b1399923c9
- src/core/contracts.ts: 6583cf95730d3e7b89d27907498ef0fcd66cce1f522d18a62992aab2e131c015
- src/core/index.ts: 65e2db342d204cd2b2055c19e6adb2dc935c10f027e726b052e5d12db4b87ca4
- src/core/approval.ts: 0493abb61f1d369c7e3b830e49e08973ebd963dc7fe23396ca380b11994675d1
- src/core/effects.ts: ead8125dbf57167b239a6364bce04975b19e964f4de233970e5d8d87e5a6ce30
- src/core/memory.ts: ea035d7dafdf05867347bc58bc42a2d3253508ad539e19174bf571065b5bf648
- src/extension/index.ts: f270168ac23b0f49be7155072790f89ab1818c7787f7b7a19524b26ee30f2c0c
- tests/effects.test.ts: bec54236f58f6ee1640d0a986f54cab4bccbfab9e4607b0d9ef262940a664329
