# Independent technical review — 2b472e2

outcome: **FAIL**. Exact source `2b472e295e09ad80bc2279099817e830c95db3b0`; durable package `delivery/zaratustra-pi-0.2.0`, tree SHA256 `7f16afbc5fc134861dac6d744090d3cd7125b740f16e62df5eb987a803a3e94d`. Previous reports remain preserved separately. New F8 blocks actual ordinary review; F7 also remains open. Owner acceptance remains PENDING. Announced corrections are not counted before a new freeze.

Latest owner scope excludes backup/recovery, source loss, shared servers, cross-device and Git data synchronization. Native Mac/Linux runs are not required. Production is unlimited; finite evaluation budgets remain explicit and separate.

## Closed earlier findings

All 64 FREEZE entries match; exact package tree matches. Twenty Python wheel members independently match frozen source hashes. Evidence: `freeze-2b472e2.json`, `wheel-source-alignment2b472e2.json`.

Independent focused source tests: `core-2b472e2.xml` / `.log` — **42 PASS**. These include real native claims and stable profile lookup after 1001 public-API records (F1), scoped reads, optional public-column projections, default paging/replay compatibility, hidden-field mutation fences, stale-session writes, native terminal handling, latest delivery/review pointers, owner-verdict separation and Sleep controls.

Actual installed Pi regression tests: `transport-2b472e2.xml` / `.log` — **14 PASS**. Tests cover public fresh review, review reopening/tool selection, rejected input, profile/hook/tool failures, command failure, cancellation during streaming, valid/missing/wrong metadata, abort, provider-error partial text and recovery from legacy metadata rejection.

One affected update check: `update-2b472e2.xml` / `.log` — **1 PASS, 6 deselected**. Actual 0.1 wheels update to current 0.2 wheels while preserving Activity revisions/history, pending Work/wait, credential/database bytes and exact refs. Unchanged bootstrap controls are not repeated; prior 7/7 proof remains separately attributed to 372245f.

Old independent counterexamples were also run on exact extracted wheels/extension (`frozen2b472e2-wheel-code/`), not mutable source. `native-2b472e2-summary.json` and respective raw scenario directories show:

- **F3 closed:** public `/zara-review` creates a different actual SDK session, retains a separate matching Core review and restores normal tools after successful completion. Seven fictional requests, no extra denied request.
- **F4 closed:** rejected second input causes no further inference/write; only two requests from the first incomplete run, one retained human message, no forbidden native file.
- **F5 closed:** actual Pi partial text with `stopReason:error` and `aborted:false` remains incomplete; no Core delivery is produced. Three fictional requests, actual error bytes retained.
- **F6 closed in tested mechanical/live continuation scope:** typed schemas and metadata correction controls pass; retained real continuation and the new independent task deliver exact settled text. No global fail-open behavior observed in the retested cases.
- **F2 remains closed:** the shortened runtime directory and supported compatibility update pass. **F1 closed** by the actual >1000 native-claim regression. Earlier review-tool observation O2 is covered by the passing reopen and successful-completion controls, with the cancellation exception F7 below.

These are overlapping focused checks and reproductions, not an aggregate full gate.

## New finding F7 / P2 — cancelling an incomplete review leaves ordinary tools disabled

Location: `pi-package/extension.ts`, `zara-cancel` handler (lines 89–99 in this freeze). It clears Core Work/mapping and `failed`, but does not reapply the ordinary active-tool set after retained review mode ends.

Independent reproduction: `native-negative-checks.py cancel-review 2b472e2 delivery/zaratustra-pi-0.2.0`, using real installed Pi `AgentSessionRuntime`, exact frozen extension/wheels and six fictional localhost responses. A builder delivery completes. Public fresh review reads the file, then returns without staged metadata, so review remains incomplete. Execute the actual `/zara-cancel` with an explicitly simulated fictional cancellation confirmation. No owner-result/acceptance confirmation is simulated.

Observed: Core mapping is `{}`, review Work is cancelled, no extension errors, but active tools are only `read`, `zara_context`, `zara_read`, `zara_result`. `zara_route`, `zara_change`, `write` and `bash` remain absent. A subsequent ordinary request cannot choose its Activity through the mandatory routing tool. `before_agent_start` does not restore tools; successful settled handling is also unavailable for the new unstaged routing Work. Reattaching with `/zaratustra` is a workaround.

Evidence: `native-2b472e2-cancel-review-summary.json`, `native-cancel-review-2b472e2.log`, `native-2b472e2-cancel-review/{stdout.json,provider-requests.json,stderr.log}`. The shipped `review-reopen` test cancels via the Core helper and explicitly reattaches, so it does not exercise this direct public-command path. Reapply role-dependent tools after successful cancellation and verify ordinary continuation without an extra attach. Reviewer makes no product change.

## New finding F8 / P1 — parallel native completion hooks collide on the host lock

Locations: `pi-package/extension.ts:15-19` and `:209-211`, `packages/app/src/zaratustra_app/pi_host.py:54`, `entry_lock.py:29`. Each observation immediately launches its own Python helper. Helpers correctly retain a nonblocking cross-process lock around the whole request. Pi legitimately completes multiple builtin tools concurrently; the adapter does not coordinate its own overlapping hook requests.

Independently inspected exact live trace `_scratch/root-native-live-proof-next/evidence/review-1792218057175.jsonl`: public review replaces the actual session, installs read-only tools/inherited eval gate and makes three actual sends. Third response contains two reads together (`label.py`, `check_label.py`). Both reads succeed, but a `tool_execution_end` observation fails `Core: resource_exhausted/native.host_busy`, causing abort. Current review remains open without staged metadata or matching report. The still-readable earlier builder delivery does not prove review completion. Derived evidence: `live-2b472e2-review-failure-inspection.json`.

Independent isolated reproduction: `native-negative-checks.py parallel-review 2b472e2 delivery/zaratustra-pi-0.2.0`. Real installed SDK, exact frozen wheels/extension, private fictional Core, no artificial sleeps/lock holders/source edits. Four builder responses create delivery; one review response contains two real builtin reads. Five fictional requests total. Same `native.host_busy` in `tool_execution_end`; stack explicitly includes `Promise.all` / `executeToolCallsParallel`. No report retained; mapping stays in review mode.

Evidence: `native-2b472e2-parallel-review-summary.json`, `native-parallel-review-2b472e2.log`, `native-2b472e2-parallel-review/{stdout.json,provider-requests.json,stderr.log}`. Retained `parallel-review-contract.py 2b472e2` requires no hook error plus a matching retained review; it FAILS on this candidate. Previous 14 cases/original counterexamples supplied one builtin call per assistant response and miss this boundary.

Impact: ordinary model-selected parallel reads abort review and can affect other turns. Preserve host cross-process exclusion/current Core checks while coordinating the adapter's own requests; do not replay unknown effects or weaken the lock. The isolated reproduction establishes this failure class, not retrospective OS PIDs in the live window or historical legacy SQLite/RPC causes.

## Independent live evidence

### Same-Activity continuation — PASS for this retained bounded scenario

`live-2b472e2-continuation-inspection.json` derives from raw `_scratch/root-native-live-proof-next/evidence/development-1792217671606.jsonl`. Source/package match; four actual sends, no trace errors. Actual tools route/read/bash/result succeed. Final Pi assistant stops normally; exact text equals Core delivery. Same `fictional-label-utility` identity, accepted=false, mapping idle. Independently inspected actual CLI install/registry/loader artifacts in `_scratch/permanent-2b472e2/pi-install/` show the durable package loads its commands/tools without an extension-path override and without model sends.

The earlier incomplete Attempt was explicitly cancelled by the leading harness, not silently retried. Root's same-home update preserves earlier fictional history. This does not claim arbitrary external effects exactly once.

### New independently selected task — PASS

Model received only `live-task-2b472e2-prompt.txt`, SHA256 `7de04c4f30131d66bce779b0ecaad1251dff072b2418b47fc388aa99b307fadf`, 434 bytes. The separate `live-task-2b472e2-rubric.json` was not sent to it. Prompt requested a one-argument CLI while preserving import behavior/checker; it prescribed no implementation.

Raw trace `_scratch/root-native-live-proof-next/evidence/correction-1792217856246.jsonl`: seven actual sends, successful settled assistant, matching actual delivery in the existing Activity and no owner acceptance. `live-2b472e2-correction-inspection.json` records independent trace checks.

`check-live-task-2b472e2.py` independently exercised the actual retained fictional files, using fresh local Python subprocesses with bytecode writes disabled. `live-task-2b472e2-rubric-results.json`: **all 11 fact checks PASS**. Original checker bytes match the pre-task baseline and actual checker exits0. Hidden one-argument invocation with tabs/newline/repeated spaces outputs exactly `QUIET LAKE\n`; import produces no output and preserves callable normalization. A read-only SQLite query of the exact fictional result/Attempt/Work independently matches the trace result/hash/text, completed status and same Activity scope. No credential table or auth file was read.

### Budget accounting

Before the new task, prior eight failed-run sends plus four successful continuation sends were retained as cumulative12. Task adds seven = cumulative19. Leading chat subsequently authorized finite evaluation ceiling35 using later owner clarification, preserving spent19/per-chain8: **an amendment from 24, not the original 24 budget**, not a reset/retry. Inspected `budget-amendment.json` records before/after and old harness hashes. Failed live review adds three = cumulative22/35; ledger halts without retry. Production stays unlimited. Actual SDK replacement-gate structural proof uses zero real sends; no universal model reliability follows. Reviewer sends zero real requests.

## Criteria still requiring final evidence

| Criterion | Current status |
|---|---|
| Exact freeze, supported update, ordinary entry, >1000 claims, projection/replay fences | PASS in tested scope |
| Native terminal/error/admission boundaries | PASS in retested scope; concurrent adapter requests fail F8 |
| Same-Activity actual continuation and new independent coding task | PASS for retained bounded traces |
| Actual independent fresh live review retained in same Activity | FAIL — F8 in live and independent fictional parallel-read scenario |
| Reopen after that live review, no inference/effect replay | PENDING |
| Live Sleep retained adaptation and observed subsequent use | PENDING; mechanical Sleep controls pass |
| Full native gate | NOT PASS — retained `gate/result.json` reports STOPPED_SUPERSEDED/exit1 after live failure, before source edits; no completed successful full-test summary |
| Cancel incomplete review then ordinary work | FAIL — F7, workaround requires reattach |
| Owner acceptance | PENDING; reserved to owner |

evidence: exact paths above. No summation of repeated tests. Native SDK fixtures use an explicit Python bootstrap seam; actual install/bootstrap/update has separate proof. Fake provider responses are mechanical evidence, not live semantics. Actual successful traces are inspected independently with no new reviewer inference.

assumptions: this report applies only to exact 2b472e2 source and package digest. New source edits invalidate its final-release alignment until refrozen. Arbitrary Pi file/shell effects remain observations. Owner acceptance differs from completion and technical review.

cuts: no source/index/commit/push/personal data/auth/secret access; no publication; all reviewer writes remain in assigned scratch. Backup/recovery and platform matrix remain outside current readiness criteria. No semantic truth validator is introduced.

cost: local focused tests, bounded fictional localhost scenarios, read-only retained trace/fixture inspection; no real model sends from reviewer. F7 is newly reported rather than silently cut from the cancelled-review path.

manual-acceptance: PENDING.

next: solmax — correct F8 and disposition F7, then supply new exact freeze, aligned completed native gate and fresh live review/reopen/Sleep evidence. Preserve passed independent task/rubric and failed review trace; no automatic paid retry. No backup/recovery work is required by this verdict.
