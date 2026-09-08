# Product RESULT — Zaratustra Work 3

call: c-solmax-zaratustra-m0-mutation-20260908-work3
engineering_contract: 36
mode: PROBA
repo: C:/projects/zaratustra
direction: solmax
node: g-zara-m0-continuity
task: t-zara-m0-mutation

## outcome

ESCALATE / W21 OWNER TRUST-CHANNEL CHOICE / WORK 3 NOT IMPLEMENTED.

The complete CALL and its named sources were read. PLAN preserves literal §5 and
identifies one unresolved owner-owned trust boundary before dependent changes.
Accepted version remains 0.2.0. No Work 3 source, migration, grants, mutation API or
test-only success path was introduced. A partial deny-all API would not fulfill the
CALL and is not presented as delivery.

The owner was asked whether separate local interactive confirmation can be trusted
for the exact displayed safe internal operation. At report preparation no answer
has arrived. Silence, the implementation request, CLI flags and generated receipt
text are not treated as runtime authorization.

The concrete proposal in docs/work3/PLAN.md shows workspace, Work, revision,
operation and SHA-256, then accepts a separate confirmation, not approval in payload
or piped input. Its trust boundary is access to that console; it does not authenticate
a human against other processes under the same OS user. Core would still check
current Work/rights, revocation and revision. Accepting that boundary is the missing
owner decision. The precise operation allowlist remains conditional on that answer.

Reason for returning: the CALL prohibits self-asserted authority and requires an
unresolved owner-owned choice to return HOME. Architecture evidence W21 explicitly
leaves the trusted surface unselected. Work 2 bootstrap creates draft Work with
authority_scope=none and grants no future rights. The development CALL authorizes
implementation and fictional trials; it is not a product credential for arbitrary
future callers. Sources: docs/work3/PLAN.md and exact copied docs/work3/CALL.md.

This is an executor-identified contract blocker, not an automatic approval rejection,
unavailable required tool, product integrity defect or global skill requirement.
No Work 3 implementation commit exists. T2/Work 3 and M0 remain open. Setup, Work 1,
Work 2 and T1 retain accepted binding G5 disposition. This report supplies no fresh
binding G5, owner runtime PASS or next Direction CALL.

## evidence

direction_commit: 5f6c8fac9910eff5a6a1b64f45f7e7e5c1570d09
product_basis_report: fe064773dccb2d1f818f1004962043df2ef1edd9
accepted_implementation_commit: ce8ae68cf555f05864c9dd6b82cfbfd9babe61b1
work3_implementation_commit: none — blocked before dependent implementation
version: 0.2.0 — unchanged accepted version, not a Work 3 release
input_branch: codex/work2-core-records
report_branch: codex/work3-mutation-plan
remote: none
report_content_commit: 6c9da9eb8213de9f5612179adc829b5192c400a7
report_locator_update: this subsequent documentation-only commit records that exact id

Only RESULT.md and docs/work3/ belong to this leg. Source, tests, tools, package
metadata, uv.lock, released migrations, AGENTS.md, REVIEW.md, validation.config and
accepted docs/work1/docs/work2/docs/setup remain unchanged. Previous full RESULT
is retained at product_basis_report. Exact final report commit ids are supplied in
the HOME message. Documentation commits are not relabeled as implementation.
Full report/PLAN/evidence content was committed at report_content_commit. The
following locator update adds its hash and HOME message; no measured product
source, tests, build inputs or raw check outputs change. A commit cannot contain
its own hash; the final locator commit is identified in the session's HOME message.

| CALL done_when | Actual disposition |
|---|---|
| 1. One Mutation API, literal §5, current Work/authority and traceable operation/revision/change/event/receipt | BLOCKED / NOT MET. W21 lacks a selected trusted runtime source. PLAN is not runtime evidence. Installed baseline confirms draft Work/none authority and initial Event only. |
| 2. Failure tests prove one repeated effect, stale conflict and denial; PLAN defines replay | NOT MET. Replay decision is documented, but no Work 3 tests or operation ran. The 30 baseline tests do not establish mutation idempotency, stale conflict or general authority. |
| 3. DB mutation/event/receipt consistency, reconstructable audit, exact installed version/evidence and native checks | NOT MET for Work 3. Native checks and installed reads pass for 0.2.0; no mutation/event/receipt transaction exists there. New failures/commit/lost-reply checks remain blocked. File publication remains Work 4. |

Actual checks:

| Command/action | Outcome | Raw evidence |
|---|---|---|
| Product Git status/branch/HEAD/remotes; read-only Direction HEAD | Exact supplied bases; no remote; only new docs initially untracked | docs/work3/evidence/repo-state.txt and repo-state-followup.txt |
| uv sync --locked in ordinary sandbox | Managed uv cache access failed; no dependency change | docs/work3/evidence/baseline-sync.txt |
| uv sync --locked with approved managed-runtime access | exit 0; 24 locked packages audited | docs/work3/evidence/baseline-sync-retry.txt |
| uv run --locked python -m tools.check | exit 0; 30 tests, format/lint/types, 2 boundaries, wheel/sdist | docs/work3/evidence/baseline-check.txt |
| preserve-and-read.ps1 from unrelated temporary cwd | exit 0; new copies read by accepted installed executables; originals unchanged | docs/work3/evidence/retained-inputs.txt and retained-inputs.json; script alongside |
| uv run --locked python -m tools.check --deliver | exit 0; 30 tests, native checks/build and report structure PASS; baseline behavior only | docs/work3/evidence/deliver.txt |

Existing managed Python 3.13.7 and locked dependencies were reused without upgrades.
The rebuilt wheel dist/zaratustra-0.2.0-py3-none-any.whl equals the accepted SHA-256:
a50f0f2d195b33a5eac08d9dd8a2479b9863cd029af703341781fb0c63d5d53c.
Installed versions were observed as 0.1.0 / 0.2.0 / 0.2.0 in separate processes.
No new independent installation or installed Work 3 trial is claimed.

| Preserved original sample | DB SHA-256 before/after | Wheel SHA-256 before/after |
|---|---|---|
| accepted-work1, solmax-work1-accept-20260907-a1/retained-trial | ec4fd2c045922578fa1344a5c126c94b0b929215efd57e93b773baf3785ca207 | 4f71d1b2aff54d8680d22e01cb58483681a69969c3c3501667e2bb5aabb9482c |
| executor-work2, zaratustra-work2-8cv9m8jt | cd8169923aa0836bf6964537f2ea59543a44fffec3d4c4d7c2104ab221759de0 | a50f0f2d195b33a5eac08d9dd8a2479b9863cd029af703341781fb0c63d5d53c |
| binding-work2, zaratustra-work2-ltyq1qsb | e6e4d430e575e17feca718b1063e6640af09103263848030bbb6d81a72905fe1 | a50f0f2d195b33a5eac08d9dd8a2479b9863cd029af703341781fb0c63d5d53c |

Full original/executable locators are in retained-inputs.json. New copies remain at
C:/Users/Anton/AppData/Local/Temp/zaratustra-work3-inputs-d25d8ace-8a7f-455a-95c0-d3188b7e72e5/.
Their DB hashes after reads equal originals. No originals/copies were migrated or
manually edited. The existing Direction backup archive was not opened or changed.

Both v2 snapshots have state_revision=1, every record revision=1, Work draft/none,
Artifact active_version=null. Exact ids/fields are in retained-inputs.txt. These
initial-record facts are not mutation permission-denial or one-effect evidence.

sources.json binds the complete named source set, previous RESULT and every Work 2
evidence file by path/length/SHA-256. Hashing establishes identity/preservation only.
No source scan replaces product behavior evidence. Code reading identifies absent
adapter/API; installed reads corroborate initial state, not a future implementation.

The first cross-repository git -C read hit sandbox dubious ownership; the exact read
succeeded with per-command safe.directory for the named read-only Direction repo.
No global Git configuration changed. No gate exhausted three retries. Required
tools work with approved managed-runtime access. No approval rejection remains.

## assumptions

Existing owner-ack:solmax-plan-conforming-20260907 permits conforming technical
choices; it does not select the unestablished trusted channel. PLAN does not
silently move duplicate lookup ahead of current authority and expected revision.
Original replay may conflict; revoked authority may refuse earlier; terminal Work
is never reopened; changed intent at duplicate stage is a collision. Separate
authorized receipt-read is proposed for lost reply; its rights depend on W21.

The proposed increment is DB-only. Unsupported file references cannot be pretended
valid. An empty affected-projection set does not prove rebuild; Work 4 must implement
publication/rebuild before admitting dependent operations. No §5 duty is removed.

| ID | Disposition / remaining answerer and rewrites |
|---|---|
| W19 | Literal-order replay proposal recorded, unimplemented. PLAN resumes duplicate/stale/terminal/collision/current authority/receipt-read after W21; Result/next unit before Works 5/7. rewrites: importer, receipts, linkage, failure tests/migrations; cheap reversal unproved. |
| W20 | Initial DB transaction retained; proposed mutation/event/receipt and lost reply unimplemented. PLAN before Work 3 completion and Work 4/7: commit/failure, publication, orphan/recovery/rebuild/late availability. rewrites: durable references, recovery/evidence/migrations. |
| W21 | BLOCKER: proposed console trust boundary has no owner decision. Draft/none/no-grant preserved. PLAN needs actual caller/receipt binding, current/revoked rights and receipt-read before mutation, then Works 5/6/7. rewrites: adapter/import/permissions; resize for different channel. |
| W22 | Initial snapshot retained; proposed global revision includes all admitted rights/status/state changes. PLAN before Work 4/6: dependency revisions, scope/freshness/budget/delivered manifest. rewrites: snapshot/context/tests; none cut. |
| W23 | No clean-chat proof. PLAN protocol before Work 6/8, actual separate input/response by five facts in Work 8. rewrites: delivery/demo; unprovable cleanliness blocks. |
| W24 | Accepted v2 unchanged; identity/fingerprint/explicit v3 proposed only. PLAN finalizes after W21 and before recovery/cleanup dependencies. rewrites: mechanics/tests/migrations; semantics return W19–W22. |
| W25 | Three preserved fictional copies, no second full Process or actual foreign-context proof. PLAN fixture before Work 5/6/8. rewrites: fixtures/tests/demo. |
| W26 | Actual bases/no-remote/version/sample hashes verified. Permanent workspace/hosting/external independent install-upgrade stay future. rewrites: package/layout/docs, reassess with outside consumers. |
| W27 | No new public seam frozen while W21 unresolved. E1/E2/E3/E6/E8/E9/E10/E11 preserved for admitted consumers; E4/E5/E7/E12 get no invented direct M0 API; no incoming M1+ prerequisite. rewrites: Core/data and consumer migrations; cheap replacement unproved. |

## cuts

No Work 3 done_when is removed or relabeled PASS. Implementation awaits the named
blocker. This is ESCALATE, not a smaller delivered mutation scope.
Work 4–8/full demo, M1+, MCP, real Process, permanent personal workspace, external
independent install/upgrade and full migration remain outside admission.

CI/CD, Actions, notifications, setup/test pushes and publication remain excluded by
owner-ack:solmax-zaratustra-work1-no-automation-20260907 and
owner-ack:solmax-zaratustra-local-setup-no-automation-20260907.
No Direction OS/old-repository writes, secret/archive reads, remote/account changes,
new expenses or external/irreversible effects. No manual DB/state Markdown repair,
bootstrap grant, next Direction CALL or automatic Work 4 admission.

## cost

One executor, no subagents: this is Work 3, not setup verification; the CALL does not
request delegation. Approximately 25–35 minutes for source reading, PLAN, baseline
checks/copies and report, estimated rather than billed. No implementation time
claimed. A half-focus-day implementation estimate is conditional on resolving W21
with a small local adapter; a different channel needs reassessment. No new deadline
or budget. Exact token/subscription cost unavailable; existing tools reused.

One uv cache failure was resolved by approved sandbox escalation; native checks
passed. Read-only Direction Git used a per-command safe.directory exception.
These access issues are resolved and are not the returned blocker.
The first report replacement patch was rejected before writing because it used
two operations on the same file; a single-file write prepared the report instead.
An extra Git whitespace check flagged trailing spaces in import-linter's native
banner in two raw logs. Raw output was preserved; the whitespace check excluding
raw text evidence passed. The repository's required native gates passed unchanged.

## manual-acceptance

Owner Work 3 runtime acceptance: not performed; no installed Work 3 exists.
Binding fresh physical G5 for Work 3: not performed. Work 8 demonstration remains
future. Previous G5 receipts are used only as accepted baseline inputs.

The concrete owner question remains:

> Принимаете для M0 отдельное интерактивное подтверждение точной внутренней
> операции в локальной консоли как доверенный канал, с границей доступа к этой
> консоли и без защиты от другого процесса того же OS-пользователя?

Full proposal, denied shortcuts and restart conditions: docs/work3/PLAN.md.
The answer concerns authority semantics and cannot establish owner runtime PASS.
Rejection requires a different specified trusted receipt source and adapter sizing.

Read-only baseline reproduction uses exact installed_command/copied_workspace
locators in docs/work3/evidence/retained-inputs.json. The saved
docs/work3/evidence/preserve-and-read.ps1 creates new copies on each run and verifies
original hashes. It is a baseline probe, not Work 3 execution instructions.

## next

next: solmax
HOME: resolve concrete W21 using this full RESULT, PLAN and raw evidence.
Do not close the Work 3 CALL/T2 or M0, infer owner runtime PASS, issue Work 4,
or remove W19–W27. After an explicit W21 decision, finalize bounded PLAN/size,
implement on new copies with explicit migrations, and verify all three original
done_when. Product does not issue a next Direction CALL or change Direction OS.

END_OF_FILE: RESULT.md
