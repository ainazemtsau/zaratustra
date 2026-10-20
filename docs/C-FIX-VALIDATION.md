# Targeted C correction after independent PARTIAL

Baseline/reviewer artifact: 0d188eee3d25ac26a24d28b5a363e5c4b75a2e7c. Independent verdict
PARTIAL remains attributed to it. Reviewer separately passed image-only/positive/mixed
EPUB, managed materials, lifecycle, upgrade, guards and both P2; those checks are not
rerun or renamed here. First block 27a74fd remains separately accepted; C is not accepted.

Fixed public code candidate: 14c4e0d263542344c9d577ef4035fefba5afcac4. One executor;
no subagents/chats, no Direction OS changes, no new D/E capability. Final delivery is
documentation/evidence only and is reinstalled with exact product-input identity.

## Established cause and boundary

The baseline Core accepts only record refs in step result_refs; prepare_handoff returns
an immutable supporting-row address. The direct ordinary API route reproduced
REFERENCE_NOT_FOUND even with the correct step claim and current Work guard. Creating
a record_result duplicate is avoidable. A narrow step-result resolver now accepts the
existing prepared handoff for that same Work, with absent revision or immutable revision 1.
It leaves the record resolver for wait Evidence, Knowledge and Work completion untouched.
There is no auto-completion, semantic intent inference, optional-step promotion or ban
on valid unfinished optional steps. Model chooses whether the artifact satisfies a step.
Preparation and step recording have separate exclusive claims/commits. Existing legacy
handoffs are reusable unchanged, with no schema/data migration or parser/dependency change.

Reopen with a new concrete wait was already supported. Updated skill/tool guidance tells
the model to preserve the old result/history, add the actual upcoming wait, and choose
waiting when no independent action is available. Core does not classify next_action text.
For an entire external-review step, preparation alone never supplies the missing input.
The new handoff refs are step grounds only; Work criterion grounds still use records.

## Evidence table

| Criterion                                               | Mechanical                                                                                                                                                                                      | Real installed model                                                                                                                                                                                                                                         |
| ------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Real saved preparation address, no duplicate message    | RED on baseline; GREEN on candidate; wrong Work/revision/missing claim/stale guard negatives                                                                                                    | 01: preparation done, one saved handoff result ref, external wait separate; 02 new-process continuation leaves entire database exact                                                                                                                         |
| Preparation versus external review                      | Pending input blocks the addressed review step; prepare_handoff itself changes neither step                                                                                                     | 01: final-card step remains waiting, preparation is done                                                                                                                                                                                                     |
| Explicit reopen for later input, history/results intact | Old completion exact; concrete new wait; active independent action allowed                                                                                                                      | 03 done rev6 → 04 waiting rev8; old result and done rev6 exact, no new artifact at reopen                                                                                                                                                                    |
| Later clarification and similar handoffs                | Addressed wait satisfaction and guards covered                                                                                                                                                  | 05: same new wait satisfied by retained clarification, updated result saved. 07–08: ambiguity question then one reply binds only Compass; other Work exact and waiting. Pair preparation is mechanical after failed 06, not a fully model-created pair story |
| Transaction recovery and old-version compatibility      | New link/claim/revision/receipt fault tests; actual native 0d188eee→candidate preserves all ten tables before changes; old writer fails closed on new refs                                      | Mechanical fixture is not a model act                                                                                                                                                                                                                        |
| LOW correction and future exports                       | 327 current original hashes and 327 derivatives exact; historical manifest/empty derivative preserved; missing historical raw explicit; sealed export positive/self-stdout/changed-source tests | No model claim needed                                                                                                                                                                                                                                        |
| Regression/install/parser identity                      | check 37/37; installed affected Work/export tests 13/13; native P2 zero requests; 22 unchanged parser/storage/dependency/fixture inputs                                                         | Same selected model/medium/native Pi auth; public installed candidate only                                                                                                                                                                                   |

[LOW history and hashes](C-PROVENANCE-CORRECTION.md). [Prior qualification](C-VALIDATION.md)
retains exact versions and incomplete runs. New live ledger is separate from both closed
ledgers: 8 attempts / 60 provider requests / USD 5 Pi estimate, never reset. RPC is an
explicitly trusted synthetic channel, not the owner. No credentials read/copied/published.
[All eight actual conversations](C-FIX-CONVERSATIONS.md) and
[raw-log readback](c-evidence/fix-20261020/live-verification-final.json) are retained.
Final ledger: **8/8 attempts, 57/60 provider dispatch attempts, USD 1.035156/5 Pi estimate**;
input 718982 (including cache_read 299520), output 16628. Four dispatches in 06 failed
transport with zero usage reported by Pi; actual server receipt/billing is unknown.
Seven attempts have actual responses; 06 has none. No timeout/budget-aborted request.
Stop by attempt cap: no ninth conversation, despite three requests remaining.
There were eight actual tool errors (03:4, 05:2, 08:2), all visible before repair.

The full model-created two-request preparation story is UNVERIFIED in this run after
06's transport failure. The missing review followup itself is now proved by actual
07–08 on a declared mechanical pair fixture; no fixture action is counted as model work.
Handoff refs are deliberately step-only: in 03/05 the model tried them, then its own
Work, as overall completion grounds; Core refused. It finally reused actual returned
Evidence, with no duplicate prepared-message record. This remaining API distinction
and model repair cost are explicit, not a universal planning/reliability guarantee.

## Exact current records and preserved history

Actual model Work: work-c6045585-05de-476d-a0db-7a7befc3d9ef.

| Point              | Actual state and addressed grounds                                                                                                                          |
| ------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 01 preparation     | rev2 waiting; prepare-message done with result_refs=[handoff-b1ffdb40-ee07-44bb-bff4-6e895774f825]; finalize-card waiting; external-review pending          |
| 02 new process     | All seven observed domain/support tables exact; no new handoff/wait/result                                                                                  |
| 03 completion      | rev6 done; saved card evidence-af043a26-dccc-48cd-a736-022a9c3d1b44; external-review satisfied; pinned completion grounds                                   |
| 04 explicit reopen | rev8 waiting; new second-sentence-clarification pending; old wait satisfied; exact rev6 completion and old artifact retained; no new artifact               |
| 05 input arrives   | rev9 done; exact new wait satisfied; clarified card evidence-81dbdbec-631f-437a-85fd-25ea8626aab3 in current completion grounds; old card/history preserved |
| 08 clarified reply | Compass work-1331d488-4402-4ba8-9d29-fb3e0e505cac rev4 done; Lamp work-a2215a5e-ea1e-4ae7-85a2-f847ac0cddc0 stays exact rev2 waiting                        |

The independent reproduction remains unchanged: work-cd59d3a4-5873-4364-8dad-f8c6739b1988
at review 0d188eee had preparation todo/result_refs empty and reopened rev8 active with
only a satisfied old wait. Its reviewer workspace was not repaired in place. Its logs
are retained as source reproduction; new records above are separate synthetic evidence.

[Provenance verification](c-evidence/fix-20261020/provenance-verification.json) checks all
327 current raw sources and derivatives. Published historical manifest SHA256 remains
faaf1bd4aace62e33a79e8f84dafa863917a7b4d76592c5d7793b17ed0774aac.
New evidence exports use sealed completed sources and a separate stdout path, validate
all source/derivative hashes, and do not include their own in-progress console log.

Open braces advisory remains a separate retained dev-dependency issue. Full R1/T31,
independent PASS and C owner acceptance are not assigned. First unimplemented product
outcome remains D, shared Concept/Entity memory and independent English discovery.

END_OF_FILE: docs/C-FIX-VALIDATION.md
