# 0.7.0 focused verification

Scope: Windows x64, Node24.22.1, Pi1.4.0. Synthetic temporary workspaces only.
No paid/model conversations or real ZT/Health changes belong to these product checks.
This report deliberately does not claim one full historical test-matrix run.

## Executed checks

| Area                               | Actual evidence                                                                                                                                                                                                                                                                                                                                    |
| ---------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Source policy and Core integration | Final combined12/12: policy8, Core3 (ordinary-success/no permanent growth, exact Unicode fragment, compact intent/replay), native SDK construction1                                                                                                                                                                                                |
| Sleep                              | Final28/28: phases, native generation refusal, persisted limits, exact Core/document permits, postdeadline settlement, dead recovery, future observation, ACL changes, metadata cancel, queued shutdown and addressed reads                                                                                                                        |
| Managed documents                  | Real native write+rename through the integrated Sleep permit; exact prior bytes retained before Git;1/1                                                                                                                                                                                                                                            |
| Native Pi lifecycle                | Independent path reservations and shutdown during native decision passed; final restore/reopen case1/1 after fixes                                                                                                                                                                                                                                 |
| Git                                | 26 distinct top-level cases have focused passing evidence across runs. The earlier full run had22 passes and one fixture wall timeout; offline/custom-home retries passed after correcting polling/fixture allowance. Later hooks/filter/fsmonitor and canonical-autocrlf cases passed separately. No single final26/26 whole-suite run is claimed |
| File durability                    | Targeted runs cover marker before/after, retired-journal cleanup, interrupted activation, process death after SQL/pre-file and file-marker/pre-coordination, missing/drifted sources, foreign cache, clone, readonly repair, exact quarantine migration, imports and bounded cache GC                                                              |
| Administration                     | Corpus-only backup, corrupted SQLite and canonical-manifest restore, semantic preview freshness, early legacy-bundle refusal and durable decision recovery passed                                                                                                                                                                                  |
| Resource collision                 | Regression first failed; final3/3 verifies both reservation row orders and UNKNOWN/live-owner collision; no live reservation is stolen                                                                                                                                                                                                             |
| Old writer                         | Baseline9ccf36 source refuses control3/schema10 and all fixture files remain unchanged; see `memory-v2-evidence/old-writer.json`                                                                                                                                                                                                                   |
| Dependencies                       | Six bounded security/contract/document/URI regressions passed after integrating prepared Zod/fast-uri updates                                                                                                                                                                                                                                      |
| Parallelism                        | Actual2 and10 separate child processes; independent Work across two Activity, same-request replay, altered intent rejection, one guarded winner and the remaining revision conflicts. See compact JSON exports                                                                                                                                     |

The ten-process profile took about61 seconds end to end; its largest measured phase
was28.1 seconds including queue wait and durable publication. It is not a throughput
promise. Peak worker RSS was sampled, not a continuous whole-machine maximum.
Separate pure queue-wait timing was not measured. No run exceeded ten child writers.

## Important defects found and repaired before publication

- Journal cleanup could remove replay images before retiring its intent.
- A cache could share a revision number but belong to a different corpus identity.
- Canonical drift or a SQL commit preceding file publication could be mistaken for saved truth.
- Interrupted activation/clone and the cross-database admission gap needed explicit recovery.
- Administrative auxiliary writes needed coordinated cache invalidation; damaged corpus needed a separately flagged local exact recovery preview.
- Native Sleep finalization needed a narrow document permit, not fabricated human approval.
- Paused phases, expired sources, deterministic refusals, closure races and timer rejection could strand a review.
- A mere later inferred record could falsely count as a benefit observation.
- Git needed exact remote/tree/parent-blob checks, portable canonical attributes and explicit external-program boundaries.

Tests and fixtures also had corrected setup issues (missing required fields, mock command
API, timeout allowance and a restored test file after an encoding error). These are not
passed product attempts. The prior23-test Sleep source was recovered exactly from its
own compiler source map before five new cases were added. No owner data was involved.
The concurrency attempts note preserves its fixture corrections separately.

## Reproduce proportionately

`npm ci`; `npm run types`; `npm run lint`; `npm run boundary`; `npm run build`.
Run the relevant new suite with `node --import tsx --test tests/<name>.test.ts`.
The concurrency harness is intentionally bounded to two/ten and uses temporary data.
`node --import tsx scripts/verify-old-writer-v2.mjs <unchanged-schema9-storage-module>`
checks the explicit old-writer fence. Do not point test fixtures at personal memory.

The old full qualification matrix and paid conversations were not repeated. Physical
power loss, malicious OS filesystem races, unbounded load, complete Pi-host security
and usefulness over years are not established by this work. Actual personal migration,
installed SHA and private GitHub confirmation must be reported by the coordinator after
its separate safe update window; this public report does not substitute for them.
