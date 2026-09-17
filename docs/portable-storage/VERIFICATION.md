# Verification — portable storage

## Completed

- Final full native delivery gate passed: 496 tests, 27 import contracts, formatting/lint,
  strict types over 165 source files, source/wheel builds and report structure.
  The earlier complete gate passed 495 tests. The first full attempt stopped at a
  Python3.13 generic-syntax lint rule; corrected. The final rerun followed the new
  reproducible connection CRLF regression, not an unexplained repeated full run.

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
- The real authorized Home was migrated with a retained file/SQLite backup; all 62
  process rows and historical material bytes matched that same baseline. Relative
  Pi configuration, complete portable data and ready-to-paste ChatGPT instructions
  were pushed to the owner's private repository. No personal content was invented.
- A fresh clone from that private GitHub repository contained no SQLite databases.
  `uv sync --locked` installed the pinned public package, ordinary commands rebuilt
  local caches, and opening/search/source reads preserved all 62 rows. A real new Pi
  chat opened the owner's process, loaded its selected rules, found the saved backlog
  and current/no-current focus. It made no writes; Git remained clean.
- The clone then pulled the final pinned correction, installed it, updated its Pi
  connection and rechecked the same baseline successfully. Git-normalized connection
  content was unchanged (Windows line-ending stat differences were refreshed in the
  test clone); no new commit or user record was created there.
- [Fictional Pi scenario evidence](evidence/pi-scenarios.json) retains observed tool
  arguments, error flags, answers and raw-trace hashes. It excludes model reasoning
  and private Home traces. This includes the first rejected guessed field and the
  successful schema-first proposal after the supplied instruction was clarified.

## Failures that informed changes

Real Git clone exposed Windows line-ending conversion invalidating source hashes.
Managed data now carries local .gitattributes preventing byte conversion, and HEAD
uses explicit merge conflict behavior. A later git add exposed Windows path length;
operation row filenames were shortened. The same Git exchange test then passed.

Preparing the actual private checkout exposed a related connection-update issue:
Git CRLF conversion could make a previously generated Pi connection look edited
at the next upgrade. A regression test reproduced the refusal. Connection ownership
now also recognizes the exact LF-normalized bytes; actual owner text edits still
refuse replacement. The final delivery gate passed for this code correction; a
bounded read-only reviewer found no blocker in the change and did not rerun tests.

The first loader invocation supplied a relative fixture path to a loader expecting
an absolute path. The corrected invocation passed; no product claim comes from that
failed harness invocation. One cache-corruption test initially retained its own SQLite
handle on Windows; it now closes that handle before asking the product to replace cache.

The first model-driven vocabulary proposal guessed considered_ids instead of considered.
Validation refused it; the agent read command.list, corrected the proposal and completed
the request. The trace is retained, not described as error-free. Supplied instructions
now explicitly require schema discovery before the first vocabulary action and name
the exact considered field. This changes instruction text, not persistence behavior.

## Limits and acceptance

The fresh clone used another directory on the same Windows computer, not separate
physical hardware. Different-process Git exchange is tested; competing changes to
the same authority need explicit conflict resolution. Existing unclassified records
keep unknown metadata rather than invented classifications. Semantic synonym review
belongs to the agent and owner, not an automatic understanding claim. ChatGPT's
actual connector permissions and its current Project settings were not changed or
verified by the local rollout. The owner must paste the regenerated instructions
into that Project. No owner acceptance claim follows from engineering checks.

The unrelated legacy catalog concurrency observation remains OPEN and UNFIXED in
../stage2b/OPEN-OBSERVATIONS.md; successful portable-storage tests do not close it.

END_OF_FILE: docs/portable-storage/VERIFICATION.md
