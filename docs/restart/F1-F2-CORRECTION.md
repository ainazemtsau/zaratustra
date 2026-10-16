# Package A: binding review F1/F2 correction

Owner authorized this bounded correction on 2026-10-16; exact words are in OWNER-LAUNCH.md. The original independent NOT READY remains valid for candidate e6277cf/source3870ac4 and is retained unchanged in evidence/f1f2/original-NOT-READY.md. This correction does not claim owner acceptance or independent re-review success.

## F1 — declaration validity is independent of the value

Invariant: every node in the finite schema declaration must be valid before any value can be admitted. Empty lists, absent optional fields and nullable values cannot skip descendants. validate_schema traverses all object fields/list items and validates their types, flags, bounds and enum declarations before validate_value reads data. This common validator is used by both C3 and C8; ordinary untyped prose remains ordinary prose.

Class sweep: tests/restart/test_binding_findings.py covers unknown/non-string nested types, absent optional descendants, nullable object/list, malformed nested nullable/min/enum and missing items. Both actual C3 and C8 submit a valid first change followed by the invalid entry; independent SQL snapshots require zero partial record/head/history/receipt/result/cursor/wait/intent effect. Valid optional/empty/nullable/filled values and free prose still commit. Existing coercion/date/decimal/duplicate-field checks remain unchanged. The targeted F1 mutant removes whole-declaration admission and must fail these behavioral rejection assertions.

## F2 — a reply releases only the active wait

Invariant: an unanswered wait is bound to the exact finished Attempt and generation that created it. C8 stores that binding in the wait body in its existing transaction. C2 verifies human origin, exact wait revision/conversation/status, current waiting Work, latest finished Attempt and matching current generation before changing wait, Work, message or intent. No new schema table or background migration is introduced. Pre-correction wait rows without a trusted binding fail closed; migration of old/user roots is outside this new-root A candidate.

Class sweep: Q1 → pause/resume → A2/Q2 → reply Q1 cannot release Q2 or admit A3; the actual Q2 reply releases it, exact command replay is stable, and A3 can then prepare. Pause and cancel reject the old answer without changing any SQL-observed bundle. Existing wrong/free reply, original exact W7, receipt/conflict and late callback fencing remain in the A suite. The targeted F2 mutant bypasses active binding; its oracle detects actual ready Work while Q2 remains unanswered.

## RED → GREEN evidence

The original counterexamples.py and probes.py are retained byte-for-byte as .py.txt; identical executable copies run under _scratch/package-a-f1f2. On unchanged e6277cf the two assertions fail (red.log/red.json). On corrected source the same two assertions pass (green.log/green.json). These are contract failures/successes, not build or import outcomes. Original 20 negative controls and proof files remain retained; the two new controls extend rather than replace them.

Focused sweep: 48 passed, 20 deselected in 53.34s, including both targeted controls; original two counterexamples GREEN. Source pin, full required native result and re-review disposition are recorded in the final PACKAGE-A-RETURN.md and measured provenance after source freeze. The first full gate on source099621b was stopped as INCOMPLETE/SUPERSEDED after exposing a stale exact trace oracle: it still expected wait body id/question without the new trusted binding. The oracle now requires the full exact id/question/attempt_id/generation bytes; no product admission or assertion was weakened. Full package A runs before the replacement final native gate. Product api/formats remain identical to099621b. Code must remain unchanged throughout final gates; delivery evidence is committed separately.

END_OF_FILE: F1-F2-CORRECTION.md
