# Public onboarding R2 T2 engineering handback

## outcome

T2 is implemented at commit
`de0efbb51475fe2f82348d9b93bb82e3512b9876`; its exact parent and fetched public
starting point is `ecb559423d3639c42bb74df7ca8a0cb16d0f1441`. Reviewed T1 implementation
`fa126a0daf0aa0f8671c04ec2209651a60158d85` is an ancestor. Product 0.17.0 adds
explicit schema 9, a common truthful Process resume state, and one explicit
Pack-compatible ordinary-Work admission through the existing Core Mutation authority.

`read_process_state` reports the unique draft/ready Work or normal no-current state.
An invalid many-current history raises `ambiguous_current_work`; no read selects a
historical Work, writes, repairs or plans. After no-current, one exact
`WorkCreationRequest` creates one ready Work and declared Artifact in the same Process
with one revision/event/receipt. It cannot reopen a completed Work or create a hidden,
sentinel or automatic continuation.

## evidence

- [T2 PLAN](docs/public-onboarding-r2-t2/PLAN.md) records W30/W31 and A07/A08 HOW,
  failure ordering, schema/history compatibility, evidence and retained T3-T7 cuts.
- Fresh `git fetch origin main` readback showed public `origin/main` exactly
  `ecb559423d3639c42bb74df7ca8a0cb16d0f1441`; the initial worktree was clean and
  the T1 implementation ancestry checks passed.
- Schema 9 adds only a migration identity for the new `work_creation` event. Tests
  migrate a real mixed schema-8 terminal-Result plus Process-material history and
  compare all domain/event/receipt/version/Handoff/Result/material rows byte-for-byte.
- The Core request/event retain exact Process, Work, Artifact, Pack, operation and
  before/after identities. One transaction advances Process/global revision, creates
  the Work/Artifact and commits its event/receipt; an injected SQLite denial rolls
  back every part.
- The trusted `process_packs` host resolves the exact registration when constructing
  and immediately before applying the request. Missing, incompatible and unbound
  Packs, changed saved binding, stale/wrong/denied requests, existing current Work and
  reused identities all refuse without another effect.
- Restarted functional evidence covers terminal Result -> no-current read -> Process
  material (advancing the global revision) -> explicit later Work -> publish/accept ->
  terminal saved Result -> no-current read. A refreshed exact replay returns the same
  durable Process receipt; changed intent collides.
- Focused command
  `uv run --locked python -m pytest -q tests/zaratustra/process_packs/test_work_creation.py`
  passed `5 passed in 1.69s`. The combined T1/Result/Pack regression command passed
  `80 passed in 24.22s`.
- Full `uv run --locked python -m tools.check` passed on retry 2 after correcting one
  unused/unsorted test import: 127 formatted files, ruff clean, strict mypy clean over
  111 source/tool/test files, all 17 import contracts, `382 passed in 148.17s`, and
  both `zaratustra-0.17.0` wheel and source distribution built.
- Final `uv run --locked python -m tools.check --deliver` passed: the same 127-file
  hygiene, 111-file strict typing, 17/17 contracts, `382 passed in 157.56s`, both
  0.17.0 distributions and the required report structure.
- The required bounded read-only setup evaluator verified the clean T1 basis,
  contract-36 PROBA surface, absent STOP/STEER, relevant module instructions and
  existing seams. This is setup smoke only, not binding Direction G5.
- Execution receipt: parent Codex task
  `01a0988b-ede6-7350-9652-a64a65b38863`; executor task
  `01a09ee1-6fef-7a81-88a3-17d6468016e5`; worktree
  `C:/my_global_workflow/64ee/zaratustra`; branch
  `codex/public-onboarding-r2-t2`.

Done_when 1: PASS in product evidence. Common Core state distinguishes exact current
and normal zero and explicitly refuses corrupt many-current; repeated reads preserve
the exact database bytes.

Done_when 2: PASS in product evidence. A later explicit request creates one ordinary
Work only after exact authorization, fresh global revision, operation idempotency,
no-current state and exact saved/installed Pack compatibility. No completed Work is
changed or reopened.

Done_when 3: product checks PASS as above; separate fresh Direction refutation remains
pending and is intentionally not claimed by this engineering report.

## assumptions

The accepted single-Process workspace model remains authoritative. The Process's
saved exact Pack reference is the Core compatibility identity; installed adapter
availability and supported contract/state are revalidated by the trusted
`process_packs` host, because Core intentionally does not import or execute Packs.

An explicit later Work is allowed whenever authoritative history has no draft/ready
Work, including after a terminal or cancelled Work. This adds no Process-complete
lifecycle meaning. The complete request grants the new Work ordinary
`work_metadata` scope only; Artifact publication still requires its later standard
authorization.

## cuts

No unified prose wizard, entry/catalog renderer, agent asset, CLI for this Python seam,
Pack planning rule, hidden init, automatic next Work, Process lifecycle, scheduler,
Resource platform, installer/updater/fence, release, private or personal workspace,
Solmax-specific behavior, external provider, paid service, push, Direction mutation
or binding Direction G5. T3-T7 remain unchanged.

## cost

Seventeen implementation/test/plan/documentation paths changed in the implementation
commit. One additive semantic migration and one focused fictional test module were
added; no runtime dependency, remote service or paid right was added. Work used local
CPU/filesystem resources. The first full gate stopped at import hygiene before tests;
the second full gate passed. No destructive reset/clean, push or release occurred.

## manual-acceptance

pending. Fictional automated evidence and the setup evaluator do not constitute owner
acceptance, binding fresh Direction G5, public release, independent-user proof or
personal use.

## next

solmax

END_OF_FILE: RESULT.md
