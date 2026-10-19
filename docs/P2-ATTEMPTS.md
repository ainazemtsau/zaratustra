# P2 attempt ledger

Original baseline: 91ab52cfcfd53bfa7041b052468e2432d432b311.
Public candidate: 7a1e409f64f0a85b3c9340286c6445f41a862fb4.
Earlier builder and independent-review attempts remain historical and unchanged.

| Attempt                                           | Observation                                                                                                                                                                                                                           |
| ------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Baseline SDK/Core reproduction                    | Both original defects reproduced. Denied import performed one watched source read and one UUID allocation, left a new material; long observed range returned VALIDATION_ERROR and Unicode boundary was split. Zero provider requests. |
| Import-only intermediate probe                    | Denied source reads/UUID allocations became zero, staging/material/domain unchanged; intentionally still reproduced the unfixed range error and split emoji. Zero provider requests.                                                  |
| Range regression RED                              | New tests against the old range implementation: 3 pass / 5 fail, retained in p2-range-red.txt. This was expected before the range correction.                                                                                         |
| Range regression GREEN                            | All 8 pass after correction; original text reconstructed and history unchanged.                                                                                                                                                       |
| Checkout native checks                            | npm run check and candidate npm run deliver pass, 18/18 tests.                                                                                                                                                                        |
| Installed checks                                  | Normal exact-SHA Pi install succeeds; corrected native SDK probe passes with zero provider requests; installed Core/P2 suite 17/17 passes.                                                                                            |
| Live 1: create                                    | 5 provider requests, real model-selected commit creates four records, four revisions, one Change and receipt, exact Russian original and English working records.                                                                     |
| Live 2: continuation                              | 2 provider requests, new process/empty transcript and SDK cwd-b; OS process cwd remained cwd-a. Successful persisted continuation, but insufficient alone for the strict process-cwd claim. Retained; not overwritten.                |
| Live 3: continuation with both cwd values changed | 2 provider requests; new OS process cwd-b and SDK cwd-b, empty transcript; genuine waiting continuation in Russian.                                                                                                                   |
| Live 4: tail                                      | 6 provider requests; new process cwd-tail/empty transcript; actual zara_read ranges start 0 and 8000 return the tail-only answer. No copied fixture answer/transcript in question or snapshot.                                        |

Live totals: 4/6 attempts, 15/30 provider requests, 94558 input tokens including
35200 cache-read, 1336 output tokens; Pi estimate USD 0.135596 / 5. No live model
attempt failed or was discarded. All four are retained with actual tool events.
The additional cwd attempt is explicitly counted. No budget reset.

Non-passing command/helper attempts (notes reconstructed from executor tool transcript):

- A sandboxed Git operation outside the allowed roots reported permission denied;
  rerunning with the owner's authorized product path under tool escalation succeeded.
- Read-only helper calls used a nonexistent src/skills path and an unquoted pasted
  attachment path containing a space; corrected to skills/ and a quoted LiteralPath.
- A Python event inspection used the Windows default codec and failed to decode
  UTF-8 Russian; corrected to explicit UTF-8. Source/output files were unchanged.
- Public evidence export attempt 1 stopped at an overly strict whole-lockfile byte
  equivalence assertion. Its partial derivative output is preserved separately in
  the isolated root. Investigation found normal Pi npm install removed exactly
  nine peer:true metadata flags in installed package-lock.json. Package versions,
  integrity and all other lock data are equal. No runtime file was changed; the
  installed working tree is explicitly reported as modified for this lockfile.
  Export attempt 2 recorded that exception but its path-hygiene guard then caught
  double-escaped machine paths in console JSON. It was preserved separately, never
  published. Export attempt 3 covers literal and escaped path variants and passes
  path/JSON/digest validation. No credential contents were part of any export.
- An explicit Prettier write invocation also named .prettierignore/.gitattributes;
  Prettier has no parser for these control files. Maintained Markdown was formatted,
  and the subsequent full native format/check/deliver passed. No product file was
  damaged or skipped by the native check.
- npm audit exits 1 for the nine high dev-tool nodes; omit=dev exits 0. This open
  advisory is not converted into a PASS or fixed by an unreviewed mass upgrade.

New original outputs remain under a separate isolated local evidence root, identified
in the handback. Public p2-evidence files are derived/path-redacted, with original
and public digests in manifest.json. Provider thinking/signatures are omitted from
the public event projection; actual tool arguments/results and final text remain.

END_OF_FILE: docs/P2-ATTEMPTS.md
