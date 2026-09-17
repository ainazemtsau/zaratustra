# Verification — portable storage

## Completed

- Full native delivery gate passed: 495 tests, 27 import contracts, formatting/lint,
  strict types over 165 source files, source/wheel builds and report structure.
  The first full attempt stopped at a Python3.13 generic-syntax lint rule; corrected.

- 48 existing focused journal/command/skill/web tests passed before final integration.
- Six initial storage scenarios passed: exact historical source after migration/clone,
  damaged cache/source handling, failed staging, vocabulary/search, external registration
  and shared creation on a clone that lacks empty directories.
- A real local Git clone/pull test now passes independent edits in two processes and
  retrieval after merging, with no transferred SQLite cache.
- Installed Pi0.85.1 loader passed current/independent session selection, owned context
  replacement, failed switch retention, stale-target refusal, restoration and progressive
  skill loading with the portable connection.
- In-session read-only reviewer found activation/retirement, cache equality, external
  mappings, old-schema scanning, artifact checks, cross-volume setup and excessive
  repeated source reads. Corrections are in the candidate and receive targeted checks.
- After request-scoped validation, the same fictional 20-document search measured
  0.369s and 202 canonical-file reads, previously 3.915s and 6123 reads. This small
  observation is not a large-history throughput guarantee.
- An installed-wheel Pi session saved an owner-requested open problem and an explicitly
  approved new tag. A fresh chat, given only the ordinary question, used open_problems
  and source.read, recovered the unknown cause/next step and wrote nothing.
- After the instruction clarification, 35 focused tests passed. A further fresh Pi
  chat read both vocabulary command schemas before use, checked existing meanings and
  proposed a new tag without creating it. Every tool call in that run succeeded.
- The authorized installation was copied with SQLite backup and relocated through the
  public Home API. Migration on that copy preserved all 62 process rows byte-for-byte
  (including binary content); process opening, search and source reading passed.
  The original installation still matched its pre-rehearsal fingerprint.

## Failures that informed changes

Real Git clone exposed Windows line-ending conversion invalidating source hashes.
Managed data now carries local .gitattributes preventing byte conversion, and HEAD
uses explicit merge conflict behavior. A later git add exposed Windows path length;
operation row filenames were shortened. The same Git exchange test then passed.

The first loader invocation supplied a relative fixture path to a loader expecting
an absolute path. The corrected invocation passed; no product claim comes from that
failed harness invocation. One cache-corruption test initially retained its own SQLite
handle on Windows; it now closes that handle before asking the product to replace cache.

The first model-driven vocabulary proposal guessed considered_ids instead of considered.
Validation refused it; the agent read command.list, corrected the proposal and completed
the request. The trace is retained, not described as error-free. Supplied instructions
now explicitly require schema discovery before the first vocabulary action and name
the exact considered field. This changes instruction text, not persistence behavior.

## Pending

Authorized personal migration/push and clean-clone verification. No owner acceptance
claim follows from engineering checks.

The unrelated legacy catalog concurrency observation remains OPEN and UNFIXED in
../stage2b/OPEN-OBSERVATIONS.md; successful portable-storage tests do not close it.

END_OF_FILE: docs/portable-storage/VERIFICATION.md
