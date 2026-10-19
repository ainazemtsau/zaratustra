# Outcome C validation ledger

Execution in progress. Only completed checks become passed. Full R1 remains open.
Accepted predecessor: 27a74fdb9e7bd826f07a9c9f1e2e3775d54f5c1f.

| Criterion                                                               | Mechanical                                 | Actual installed Pi/model |
| ----------------------------------------------------------------------- | ------------------------------------------ | ------------------------- |
| Nested Work, dependency graph, required children, terminal grounds      | tests/work.test.ts                         | pending                   |
| Partial waits and independent action; empty-transcript continuation     | tests/work.test.ts                         | pending                   |
| Pause/cancel/explicit resume/reopen with history                        | tests/work.test.ts                         | pending                   |
| Claims, revision conflicts and update bypass negatives                  | tests/work.test.ts                         | pending                   |
| Handoffs, partial/late replies and external authorship                  | tests/work.test.ts                         | pending                   |
| TXT/Markdown, multi-page PDF, multi-chapter EPUB, originals/text/ranges | tests/materials.test.ts                    | pending                   |
| Parser errors/limits, pre-access denial, async revoke, import faults    | tests/materials.test.ts                    | native SDK pending        |
| Exact predecessor upgrade, old writer rejection, data/receipt survival  | fault tests passed; actual install pending | pending                   |
| First-block/P2 regressions, check/deliver and exact public installation | 30 tests passed in first full check        | pending                   |

Live budget (one ledger, no reset): 24 attempts, 140 provider requests, USD 15 Pi estimate.
Recipient openai-codex/gpt-6.1-sol; thinking medium. RPC controller is explicitly trusted
synthetic ingress, never the real owner. All attempts, including failed setup, are retained.

END_OF_FILE: docs/C-VALIDATION.md
