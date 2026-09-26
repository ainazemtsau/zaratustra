# Owner delivery policy — 2026-09-26

Source: owner's latest message in the coordination chat.
Target: first working Zaratustra Core by the evening of 2026-09-27 Minsk time.
This is the target deadline, not evidence that delivery has occurred.

## Non-negotiable scope

Preserve the entire agreed first-release composition and the quality of its
domain model, module boundaries, authority, addressable history and maintenance.
Do not replace functionality by stubs, toy special cases, opaque free-form JSON
or a second source of truth. The ordinary intended user path must work:
start ordinary Pi, create Activity/Work/Method from a meaningful request, execute,
ask/answer, retain results, continue after restart and change the working plan.
Memory, Sleep and change/apply/rollback remain required, not optional cuts.

## Proportionate validation

- Keep runtime structural contracts. User/model prose quality is not a
  deterministic validator's responsibility; no keyword semantic gate, LLM judge,
  artificial oracle or benchmark platform as a release prerequisite.
- During implementation run the relevant tests, types and boundaries; run the
  existing full gate once on a completed coherent code package. Repeat only
  checks affected by later code changes or concrete failures. A Markdown-only
  attribution change does not require another full test/build cycle.
- Do not delete/skip existing tests to obtain green. Reduce redundant execution
  and speculative new tests, not reporting honesty.
- Review one coherent package. Findings must name a concrete violated contract,
  a reproducible case, and ordinary-use/data/effect impact. Severity labels alone
  do not decide whether delivery stops.
- Blocking: normal intended usage cannot proceed; structural architecture is
  weakened; data loss/corruption, unauthorized effects, blind duplicate sends or
  false success are demonstrated. Fix the proven defect.
- Non-blocking: cosmetic differences, nicer diagnostics, speculative cases and
  rare combinations without those impacts. Record and repair from use; do not
  create another mandatory review loop solely for them.
- No compulsory mutation experiments, all-combinations failure matrices,
  repeated whole-class sweeps, or a new approval at every internal subpart.
- Do not treat an incomplete or failed check as PASS. State the practical limit
  briefly and decide continuation from its impact on the intended use.
- Do not reopen prior accepted work merely to seek another possible edge case.
  A new concrete material defect still requires handling.

## Structural health check (Pulse)

As part of the release/user-operations package, provide a small model-free,
read-only command that checks structural consistency and reports addresses:
references/revisions, outstanding operations, ownership/reserves, pending
maintenance and persistence of ordinary work. Reuse existing Core inspection
and audit APIs. Cover changed records since a checkpoint plus their dependencies
and unresolved earlier findings; do not ignore yesterday's open issue.

Pending/waiting/unknown can be valid states, not automatically corruption.
Never infer external success or auto-rewrite historical outcomes. A finding
creates a repair task with evidence; repair uses normal authorized operations.
First provide manual invocation; startup/daily integration should remain optional,
bounded and should not block normal launch for non-critical observations.
Do not build a separate scheduler/agent platform for Pulse.

## Work organization

One implementation chat owns one coherent functional package and its corrections.
Do not pause for approval of routine internal reversible choices already covered
by the specification. Return one concise handoff with exact code SHA, actual
checks, remaining limitations and the next functional package. Preserve the
entire remaining scope; any deadline miss must identify what is incomplete and
why, rather than silently shrinking the product.

END_OF_FILE: DELIVERY-POLICY.md
