# D qualification ledger

Implementation qualification is in progress on the third owner-authorized block.
Independent D review and owner acceptance are pending. Accepted C is e24b2fda.
This document will record exact public/installed candidate identity and M/L results;
no not-run criterion is treated as passed.

Executed before publication: memory suite 10/10; full baseline initially 42 PASS,
two environment skips and two test-fixture failures, retained in tests-01.log.
The fixtures were updated for derived indexes/schema 3, preserving tested behavior.
First memory suite 7/9 exposed source restriction and repeated-close issues; fixed
memory-02=9/9 and expanded memory-03=10/10. Both original failures remain retained.

Fixed scale corpus has 96 Concepts, 128 Entities and 2,048 claims: 2,273 records
including its single original Evidence, depth 12, wide branches, multiple parents,
ambiguous aliases, two contested claims, an old revision and wrong classification.
scale-03 completed: 41 pages, all 2,048 claims exactly once, 789,877 page bytes.
Measured checkout navigation/read path: map 544 ms/1,769 bytes, branch page 37 ms/
7,647 bytes, lexical 49 ms/940 bytes, selected claim 32 ms/1,235 bytes, snapshot
43 ms/533 bytes. These are single-run observations, not general latency guarantees.
Installed-candidate scale qualification will be recorded separately.

Early scale-01 had a duplicate developer-script variable; scale-02 had an incorrect
observer envelope path. Their logs remain; no model requests occurred. Filled native
e24b2fda seed succeeded, including original bytes, revisions, historical completion,
reopen/wait, claims, immutable handoff and replay receipt; upgrade verification pending.

Live budget is unspent: 0/24 attempts, 0/180 dispatches, USD 0/15 Pi estimate.
All future runs use one persistent ledger; actual provider billing remains unknown.

END_OF_FILE: docs/D-VALIDATION.md
