# Stage 2A — work journal, revisions and grounded continuation

## outcome

Candidate 0.19.0 continues Stage1 commit
079bf616cacbbea43a94537f7e6a89c674cc9086. It adds registered record types,
immutable record/document revisions, distinct decision operations, explicitly shared
Home records, scoped FTS5 retrieval and standalone exports through Pi and the common
API. The shipped journal instruction supports agent-initiated meaningful logging
within the owner's agreed rule. Core/Stage1 storage formats remain unchanged.

The owner approved the v3 scope plus seven supplied clarifications with «да».
Implementation decisions and constraints: docs/stage2a/IMPLEMENTATION.md.
The previous Stage1 report is retained in docs/results/2026-09-16-stage1-home.md.

## evidence

Full `uv run --locked python -m tools.check --deliver` passed: 464 tests in 230.28s,
168 formatted files, Ruff, strict mypy over 143 files, 22 import contracts,
wheel/source builds, hygiene and report structure. This includes 16 new behavioral
tests for journal, revisions, type registration, transitions, scopes and export.

Seven real installed Pi sessions demonstrated automatic episode logging,
owner-authorized adoption, fresh exact/paraphrased search with source opening,
an absent-answer query, correction preserving the decision, explicit replacement,
sharing, separate exports and foreign-source refusal. There were 76 tool attempts:
74 successful and two safely refused/recovered concurrent operations. One hit a
Core revision conflict; another observed shared storage while it was initializing.
Both recovered, and installed API verification found no duplicate operations.

Independent installed API checks confirmed episode revisions 1–2, decision 1–3,
unchanged earlier decision, zero Works, local package with seven entries, shared
package with one entry and one explicitly excluded local source. Standalone CLI
opened the package from a directory without Home configuration. Codex exercised
the same common installed API. See docs/stage2a/VERIFICATION.md.

Read-only in-session evaluator found two export pagination defects. Both were
verified and repaired, with a regression covering 22 records and 672 links.
Bounded re-review passed. This is an in-session smoke check, not a fresh Direction G5 review.

## assumptions

One trusted local OS owner (existing W21). The model interprets current instructions
and agreed journaling rules; saved text grants no authority. Host-call references
are actual available provenance, not invented owner message ids. Authority-source
descriptions are not a security boundary against arbitrary same-user code.

## cuts

Scope is Stage2A only. No local skills version management (2B), concrete extension
platform (3), vector service, coordinator, autonomous execution, live export import,
general document editor or automatic merge. FTS5 provides lexical prefixes; Russian
morphology and arbitrary meaning matches are not promised. Large-history throughput
is not measured. Concurrent writes can refuse and require an exact retry; initial
shared-store setup can briefly be unavailable to another caller. All demonstrations use
fictional content. Personal Development content remains the owner's choice.

## cost

One implementation branch; one bounded read-only evaluator smoke. Existing Python,
SQLite and Pydantic dependencies reused. No paid service, usage reset or external
rights purchased. Actual Pi checks use the configured account and a separate local
runtime/Home, preserving the Stage1 demonstration and installation.

## manual-acceptance

The owner authorized scope, not yet final behavior. Developer-run installed Pi
proof is separate from personal acceptance and binding fresh Direction review.
No older Direction task is closed by this product report.

## next

solmax

Show working behavior, final checks and observed limitations, then stop.
Do not begin Stage2B automatically. This report makes no public push/merge claim.

END_OF_FILE: docs/results/2026-09-16-stage2a-journal.md
