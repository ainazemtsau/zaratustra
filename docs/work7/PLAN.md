# Work 7 — atomic Result and continuation

call: c-solmax-zaratustra-m0-result-20260908-work7
mode: PROBA; engineering_contract: 36
base: 2fa3111666139eef3ae699319444809fce563ead
actual_checkout: C:/projects/zaratustra/_scratch/work7-result
branch: codex/work7-result
direction_main: 3b9db6e2460dcf271e95b3937f4d123dbd9e2c04
status: technical plan before implementation; fictional content confirmed by owner

## Authority and size

The issued CALL, current T6 and closed T5, bet, CHARTER, osctl context, Work6
close receipt, Product AGENTS/validation.config and Works1–6 contracts were read.
Authenticated remote main equals the issuing checkout above; local main and the
default solmax worktree are older and were not treated as current authority.
Architecture sections 3–7,10,25,28–29,41–43 (canonical SHA-256
4f90d19fc742ab616301b6b4121880f76c75faaeb1f606c8190a84853d8b3e0e),
converge-arch W19–W27 and CONTRACTS C01–C08/E1–E12 support the comparison.
Existing conforming-HOW permission is owner-ack:solmax-plan-conforming-20260907;
W21 exact words are docs/work3/OWNER-DECISION-20260908.md. Both no-automation
acknowledgments remain. Technical checks are not owner acceptance or fresh G5.

One effect: finish one Work and durably create its next Work. This requires
removing the old single-Work assumption from record/journal validation, selecting
Work/Artifact by explicit identity, and compiling the exact inherited grounds.
It does not require a Process membership API, scheduling or a new dependency.
Estimated within a focused half-day for this cohesive change, native failure
checks, installed proof and backup/restore. Reassess if this minimum proves larger;
no hidden reduction of scope, additional deadline, expenditure or continuation leg.

## W19 — accepted effect and identity

submit_result delegates to apply_mutation, with request version 4 and operation
submit_result. Its value contains an immutable source_revision, exact registered
result Artifact/version/hash, ALL current Work acceptance ids in journal order,
and a complete NextWork value: explicit Work/Artifact ids, goal, expected result,
acceptance, boundaries, budget, requirements, Artifact title and authority_scope.
No inferred content, default goal or automatic copy of an owner's criteria.
The next scope is explicitly work_metadata: current metadata and the historical
grounds granted by this exact confirmed transition. Publishing needs a later
exact authorize_artifact operation. No executor is launched by submitting/opening.

One BEGIN IMMEDIATE commits the source status=done, its revision, next Work and
declared Artifact, an immutable Result record/link, event and receipt, with one
global revision increment. A unique source Work constraint prevents two Result
effects; next identities must be new. The next Work is ready only because its
complete value and scope were separately authorized with this exact request.
Old acceptances are historical grounds, not fabricated acceptance of the new Work.
The new Work has its own criteria; the Result retains the old acceptance ids,
source Work/Artifact images, source revision and exact content closure.

Literal order stays input -> current Work/authority -> expected global revision
-> duplicate -> Artifact references -> DB mutation/event/receipt -> projections.
No duplicate-first exception. Work5 canonical requests/fingerprints and immutable
source_revision/replay semantics stay byte-compatible. Submit fingerprint includes
all new meaning; only operation_id and transport expected_revision are excluded.
First submission requires source_revision=current expected revision.

A completed Work cannot submit again, even with the original id or a new id;
the current-status check refuses before revision/duplicate. This is a documented
terminal refusal, not a lost effect. Before completion stale requests conflict;
a reused committed id with different meaning collides only after authority and
revision pass. Cancelled/revoked Work keeps the old refusal. authorize_work never
reopens done/cancelled. Unknown outcome is discovered using exact authorized
result-read/receipt-read on the source Work and original operation id, never a new
operation or terminal reopen. Current metadata rights are required for discovery;
revocation refuses disclosure. Owner-local history remains an audit surface.

## W20 — durability, failures and recovery

Result refers to already published immutable content; large bytes do not enter
the DB. Work4 versioned bytes -> hash -> registration/active transaction remains.
Before accepting Result, validate every acceptance and the complete publication
reference closure, including physical bytes; no manifest-only acceptance.
No Result/next record is committed when this validation or the DB transaction
fails. A pre-existing published version is retained, never silently deleted.

DB failure before commit leaves neither completion nor next Work. Failure/lost
reply after commit leaves both, recoverable by result-read and then fresh open
of its next_work_id. A projection failure returns the committed receipt with
rebuild_required, as before. Explicit deterministic rebuild changes no DB state.
Discovery returns historical metadata, not a claim about current bytes. Next
open rereads every mandatory version and refuses late loss/corruption separately.

The only new done-state administrative write is exact restore_artifact under
the source Work's retained current artifact scope; it cannot change status,
content identity, active version, Result or continuation. This is repair of an
already registered version, not renewed execution. revoke_work also remains
available. Cancelled/revoked denial is unchanged. Exact repair/quarantine/orphan
behavior uses the existing file API. Every such repair increments global revision
and invalidates old context. Missing current repair authority requires a faithful
retained backup restore into a NEW selected copy, not direct DB edits.

Tests distinguish rollback, committed reply loss, projection failure, orphan
exact retry, collision, late loss, exact repair and restore. SQLite local Windows
failure model is retained; no new power-loss/disk-loss or hostile-user guarantee.

## W21 / W22 — current consumer rights and historical closure

prepare_authorization selects the exact requested Work in the validated graph.
Existing separate console confirmation or actual prior-permission local-chat
binds type, path and the complete request, including all next content and rights.
Files, model output, approved flags, receipts, text/URI links and projections are
data only. No accounts, identity ceremony or same-OS-user isolation is added.

Work identities are explicit. One Process contains a chain of Work/Artifact pairs,
with one initial creation event; journal replay reconstructs each pair and every
Result-created pair, and validates each global step and the complete membership.
Only the touched Work's revision changes; it equals that event's global revision.
The expected revision is always the global state revision, not the possibly older
Work revision. All managed mutations conservatively invalidate every old query.
No new mutable membership API or probe-only membership behavior is introduced.

For the original Work, open output semantics are unchanged. For a continuation,
the mandatory package contains current Process/Work/own Artifact; its incoming
Result with exact source before/after, next creation, confirmation and receipt;
every acceptance captured from the source, and any acceptances committed for the
current Work; the exact submitted result and complete historical content closure.
Inherited references are a finite grant recorded by the confirmed Result, not
permission to read arbitrary other Work content or later versions of its Artifact.
All same-Work committed acceptances remain, with no latest-wins policy. A later
consumer uses its own current rights; inherited decisions preserve their historical
effective revisions and do not pretend the source Work is still executing.
Revoking the source after completion does not revoke a separately granted next
Work; revoke that consumer explicitly to withdraw its rights. This is grant scope,
not a capability inferred from a link.

Any query reference must be own-Work content or an exact granted historical
version/hash. Every publication edge is checked, even for a visited target.
No arbitrary ancestor namespace is granted. Metadata provenance is included only
through these validated recorded edges. Empty own Artifact is valid immediately
after next creation; incoming Result supplies mandatory grounds. No omission of
current acceptances, authority, criteria, grounds or raw content for budget.

The Work6 two-pass compiler remains: collect a validated snapshot and bytes;
compile; under BEGIN IMMEDIATE revalidate caller/current scope/global revision,
full snapshot/journal/membership/acceptances/Results/descriptors and every included
byte, then compare the complete collection. Physical loss may not bump revision.
Freshness ends at final validation, not a lease for later execution.

## W23 / W24 — public wire and schema

Product 0.7.0; new explicit migration 6 adds Result storage with unique source and
next Work links. Released migrations1–5 remain unchanged; init stays schema1 and
default explicit migrate target stays4. Only --to6 on a new selected Work6 copy
admits Result. Old schemas retain their old operations/read behavior.

Public Core: NextWork, ResultSubmission, submit_result, read_result and the
existing MutationRequest/ReceiptQuery/ContextQuery. CLI: zara result submit
<workspace> <request-file>, zara result read <workspace> <receipt-query-json>;
each obtains exact separate console authorization. The submitted file is bounded
JSON data. zara work open is the same command for the next explicit Work id.
Result read is durable metadata discovery, not the live context endpoint.

Canonical context wire includes envelope, actual sources, manifest and final LF.
Raw content stays exact base64 plus hash. The entire-output size fixed point and
hard explicit max_bytes remain; overflow returns no partial stdout or implicit
increase. Human effort budget is separate. Save exact input/output and external
hashes, queries, effective/current revisions and actual source manifests. Work8
owns the real separate clean-chat delivery, response about five facts and owner
demonstration; automated reconstruction here proves recoverability only.

## W25 / W26 — selected fictional trials and preservation

New isolated checkout is above, exact accepted Work6 base. Old Work5/Work6 refs,
checkouts, DBs, wheels, receipts and evidence are preserved by before/after hashes.
One new installed trial is copied only from the accepted Work6 main workspace,
or its docs/work6/INSTALL.md restore. Negative copies are labeled diagnostics,
never main. No second full Process, real personal data or permanent workspace.

The historical observation/decision/basis bytes come unchanged from Work6's
retained-trial.zip (1657d3a559ba1275ea010b5d83ff0cb818ba26fa74ab195cc86f8218ac57d539).
Exact next fictional content was confirmed by the owner: see OWNER-FIXTURE.md.
This permits the fictional trial, not real Work content, runtime acceptance or
closing T6. Its exact text will be retained in the submitted request.

Native tools.check and --deliver, focused hidden-state failure tests, installed
runtime from an unrelated cwd with -I, source/wheel/installed hashes, actual
console confirmation, restarted discovery/context, and full backup extraction
with files AND directories are the evidence. Old acceptance/G5 input bytes are
reused only for unchanged claims, never for new Result semantics.

## W19–W27 handback responsibilities

| ID | Decision / remaining answerer and moment | rewrites |
|---|---|---|
| W19 | Product PLAN before submit: atomic effect, identity/current revision/terminal discovery above. Real owner-content awaits actual owner words. | journal, importer, receipt/linkage and failure semantics; cheap reversal unproved |
| W20 | Product PLAN before writes: existing publication then atomic Result/next, discovery, repair and restore above. | durable refs, recovery, evidence, migration |
| W21 | Product PLAN before consumer: exact request/path/next binding and finite historical grants; owner before any real new content/right. | permissions, adapters, consumer boundaries; trust decision is not runtime PASS |
| W22 | Product PLAN before context: global invalidation, per-Work journal, all current acceptances and finite historical closure, full revalidation/budget. | snapshots, context, tests, migration; no freshness/scope/budget cut |
| W23 | Product PLAN before handoff: retain exact delivered bytes/manifest. Product PLAN/owner at T7 for actual clean session/five facts. | delivery, demo, possible Work8 repeat |
| W24 | Product PLAN before implementation: version4 request, explicit schema6, identity/serialization/SQLite5s BUSY/old migration defaults above. | mechanics, tests, migration; semantics return W19–W22 |
| W25 | Product PLAN before fixtures: new copies of one accepted fictional graph; owner confirms exact next-content. T7 actual demo remains later. | fixtures, tests, demo |
| W26 | Product PLAN before start: new checkout and installed trial, preserve all previous evidence. Owner before permanent/hosted/independent external installation. | package, layout, instructions; no new external rights |
| W27 | Product PLAN before new consumer: only Result, next Work and context seams needed for C01–C08. Future consumer PLAN at separate admission for E1–E12; E4/E5/E7/E12 have no invented direct M0 APIs. | public Core/data and future consumers; cheap replacement unproved |

HOME is solmax. No Product handback closes Direction T6/CALL/M0 or issues a
successor. Fresh physical G5 of the exact final candidate is still required for
the three behavioral claims. No Work8, M1+, transport/MCP, memory/router/frontend,
autonomy, external upgrade/full migration, remote/publication/spend, CI/CD/Actions
or notifications are admitted. No live Direction or archive writes.

END_OF_FILE: docs/work7/PLAN.md
