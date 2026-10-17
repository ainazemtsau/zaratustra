# Read-only adversarial review of the decision proposal

Reviewed draft: `_scratch/permanent-bc95ceb/SLEEP-CONTINUATION-PROPOSAL.md`, exact current product `bc95ceb412210e5bb8355e60cdff537088fdf25a`.

outcome: **A is a sufficient minimal direction and B alone is not. The draft needs three bounded corrections before owner approval, plus one finite-zero clarification.** No new table/graph or complete redesign is needed. No implementation/state/model request is authorized by this review.

The independent two-case reproduction in `sleep-restart-bc95ceb-reproduction.json` already confirms both completed+remaining and fully analysed fixed cutoff+new-arrival restart. Exact predecessor progress plus generic Work lineage addresses both without rewriting results or inventing semantic analysis. The proposed same-window versus new-window distinction is correct. Generic message cutoffs must remain distinct from event-source cutoffs, as the draft already says.

## 1. Required compatibility correction — persistent old-writer fence

The promise that unsupported capability fails before mutation is not implemented by package/Core introspection advertising alone. Current old Core accepts unknown `format:'sleep-progress/v2'` as ordinary data and still writes/reads the same space. Independent public-API illustration: `proposal-old-core-v2-opaque-bc95ceb.json`; user_version0 and a deliberately incomplete future-format record are admitted. This is expected under today's contract and is evidence about the proposed compatibility boundary, not a new current-product defect.

Current `lifecycle.compatibility` admits only the exact old schema and `PRAGMA user_version=0` on every transaction. Therefore a narrow existing-mechanism solution is available: **explicitly activate a durable capability/schema generation that old Core already rejects before any v2/link commit**. A user_version generation/compatibility marker that the old transaction check actually refuses can do this without a new table. The plan must name this explicit data-capability transition, new-Core old/new admission, automatic pre-update verification and mixed-history maintenance behavior. Existing v1 record/result/receipt bytes stay unchanged. Do not promise safe downgrade or unchanged user_version0 while introducing v2 authority that old Core ignores.

Bounded replacement wording: “No new table is required. First v2/late-lineage use occurs only after an explicit compatible data-capability transition with a durable old-writer fence, checked on every transaction; an old binary must refuse before mutation. Existing immutable v1 bytes are preserved. Capability advertising is discovery, not the fence.” Add one actual-old-wheel refusal check after that transition. This satisfies the draft's existing fail-before-mutation promise rather than adding an unrelated upgrade requirement.

## 2. Required wording correction — no history is different from missing history

“A missing predecessor means an honest initial range from zero” conflicts with rejecting missing predecessor refs and can silently restart an established continuation when a record was deleted/unavailable or discovery missed it.

Bounded replacement: **“Only an Activity with no established eligible checkpoint/lineage may start an initial range from zero. If an explicit or established predecessor is missing, unavailable, inconsistent or ambiguous, return the exact blocker; never fall back to zero. Cancelled/unknown Works do not supply an analysed boundary, and their existence does not authorize guessing one.”** Existing historic roots need an explicitly selected/adopted basis where ambiguous. This preserves the draft's intended fresh-Activity behavior without turning lost proof into reset permission.

## 3. Required admission correction — CAS the progress head, not only the Work

Expected parent Work revision does not detect a changed progress head. App `_checkpoint` writes a new ordinary progress revision after the result and need not advance parent Work revision. Thus a stale exact progress reference can pass parent CAS unless the admission explicitly fences the selected progress head, losing a later valid remainder/analysis revision in the new chain.

Bounded replacement: **“Within the same transaction, require the explicitly selected progress revision to equal the expected current progress head at admission, alongside expected parent Work revision and exact terminal result/Attempt hash. Revalidate its structural invariants; freeze that exact revision into the child basis. After admission the stored predecessor reference remains immutable exact evidence, not a moving latest pointer.”** A racing checkpoint/head revision must yield stale_basis before child creation, unless the competing command already committed the same discoverable child. Do not rewrite the old result to pretend it named a post-terminal checkpoint; the new late-continuation receipt binds that newly verified exact checkpoint.

This is a clarification of the draft's single-transaction/CAS promise. App progress initialization remains separately idempotent/discoverable; parent/result/slot commitment cannot depend on process-memory progress.

## 4. Finite-zero clarification — current Work cannot carry call_limit0

Work.call_limit is currently Positive-or-None. If the parent's unspent finite remainder is0, the proposal cannot instantiate a descriptor with0, None or a large substitute. State the narrow behavior: **preserve completed parent/spend/proof and return recorded/derivable exhaustion with no child dispatch; do not create an invalid zero-budget Work or reset the policy.** If a durable paused zero-budget child is desired, that is an additional explicit shape/status change to approve, not necessary for this minimal proposal. Reuse existing resource evidence/receipt semantics rather than promising a new failed-command receipt contract.

## Scope/complexity assessment

- Keep A and current tables. The existing generic continuation link/command receipts and Core reference closure are the right authority; an adapter cursor file or separate authoritative activity checkpoint registry is unnecessary.
- Reusing `_next_work` constructor/resource logic is sensible, but late admission needs its own completed-parent checks and backup closure discrimination. Do not weaken the old rule that an original next_work link is named by its original outcome. A late-link receipt supplies its own proof while occupying the same checked successor slot.
- The draft already correctly refuses cancelled/unknown evidence, conserves resource remainder, keeps original Method/evidence attribution, and treats analysis as an assertion. Preserve exploration/unknown coverage via the predecessor in **both** transitions, not only old-cutoff remainder. Fully processed history does not mean fully understood environment.
- The new-window prefix validator must use the verified old-cutoff boundary; carrying only a scalar cursor or copying foreign manifests under the new Work would violate the current guards. Reference inheritance is the bounded solution, with maintenance closure; no need to copy every historic material into each prompt.
- “No automatic model send”, ordinary work between passes, exact mixed v1/v2 upgrade, single-successor concurrency, crash recovery before/after progress binding and prior completed result replay are sufficient focused acceptance controls. Do not turn this decision proposal into a semantic test authoring framework or add a required useful finding.

No other material contradiction found in the A/B authority model. Once the three corrections and finite-zero behavior are explicit, the owner can approve a concrete workable option without being asked to approve the entire eventual implementation in advance.

evidence: independent restart cases; read-only source review of current Work/commit_outcome/progress/reference compatibility contracts; one public old-Core future-format illustration. No real requests or actual user-space modifications.

assumptions: the owner will select the exact durable generation/late-link public shape in the implementation plan. This review does not mandate a new table or automatic migration.

cuts: product and proposal read-only; all notes/fixtures in assigned scratch. No source/schema change, real model, retry, cancel, ordinary task or publication. Actual budget33/46 remains unchanged.

manual-acceptance: PENDING.

next: solmax — incorporate the bounded corrections into the owner-facing concrete proposal before requesting material Core approval.
