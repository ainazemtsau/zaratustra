# Product RESULT — Zaratustra Work 3

call: c-solmax-zaratustra-m0-mutation-20260908-work3
engineering_contract: 36
mode: PROBA
repo: C:/projects/zaratustra
direction: solmax
node: g-zara-m0-continuity
task: t-zara-m0-mutation

## outcome

WORK3_IMPLEMENTED_AND_LOCALLY_VERIFIED / REPORT HOME.

Version 0.3.0 implements one post-bootstrap Core Mutation API with literal §5
ordering, current Work/authority checks, expected revision, operation identity,
atomic mutation/event/receipt persistence and authorized historical receipt-read.
The admitted operations are authorize_work, revoke_work, set_work_requirements and
cancel_work. They touch only the existing Work's internal rights/status/executor
requirements; goal, acceptance, boundaries, budget, Process membership and artifact
content cannot be edited through this API.

The earlier W21 ESCALATE is superseded by the owner's explicit decision, preserved
verbatim in docs/work3/OWNER-DECISION-20260908.md. A separate interactive local
console confirmation is accepted for M0; accounts/login, proof of human identity
and protection against another process of the same OS user are not required.
File text/model output does not grant permission. Already-authorized trusted local
chat application code can supply the separate in-process authorization without a
second identity confirmation. This is a library seam, not a shipped chat/Handoff
transport or a free CLI assertion of approval.

Executor native checks and the installed terminal trial passed. These are local
engineering results, not owner runtime acceptance or binding fresh physical G5.
The owner explicitly said the W21 answer is not acceptance of Work 3.
Setup/Works 1–2/T1 retain their accepted status. Product does not close Work 3/T2/M0,
issue a Direction CALL or begin Works 4–8.

## evidence

direction_basis: 5f6c8fac9910eff5a6a1b64f45f7e7e5c1570d09
accepted_product_basis_report: fe064773dccb2d1f818f1004962043df2ef1edd9
accepted_work2_implementation: ce8ae68cf555f05864c9dd6b82cfbfd9babe61b1
previous_w21_report_content: 6c9da9eb8213de9f5612179adc829b5192c400a7
previous_w21_report_locator: 085e402e17d9d68e579622941c4fb9ada53e531a
implementation_commit: c4c795815169e3a38352b09d94cdeba15134f2b1
report_content_commit: 5dce7fd665439968e46ee0725004be3bb5563eb7
branch: codex/work3-mutation-plan
version: 0.3.0
remote: none

Implementation diff: 25 files, 1558 insertions, 101 deletions.
Exact diff: git diff 085e402e17d9d68e579622941c4fb9ada53e531a c4c795815169e3a38352b09d94cdeba15134f2b1
Raw stat and full patch: docs/work3/evidence/implementation-030.txt and
docs/work3/evidence/implementation-030.patch.
The preceding W21 report commits contain no product source changes relative to
accepted Work 2. The following delivery commits contain only RESULT/HOME and raw
evidence/commit locators; measured source, tests, package/build inputs and the
implementation PLAN/owner instructions remain at implementation_commit.
The report_content_commit contains the full report and evidence. Its exact hash is
added by a subsequent documentation-only locator commit, whose hash is available
from git rev-parse HEAD; a commit cannot contain its own final hash.

wheel: dist/zaratustra-0.3.0-py3-none-any.whl
wheel_sha256: 860804660548cd20bbd976f96bf5d27fe21855a56406b5bc7c7dcbe0ab08c1f2
installed_trial: C:/Users/Anton/AppData/Local/Temp/zaratustra-work3-gnt5ksg0
installed_command: C:/Users/Anton/AppData/Local/Temp/zaratustra-work3-gnt5ksg0/venv/Scripts/zara.exe
installed_workspace: C:/Users/Anton/AppData/Local/Temp/zaratustra-work3-gnt5ksg0/workspace
runtime: Windows; managed Python 3.13.7; SQLite 3.50.4; Pydantic 2.13.5.
uv.lock changed only product 0.2.0 -> 0.3.0; no dependency was added or upgraded.

| CALL done_when | Local measured verdict / evidence |
|---|---|
| 1. Single Mutation API, literal §5, current Work/authority and traceable operation_id/expected_revision/change/event/receipt | PASS in executor checks. mutations.apply_mutation revalidates schema, then Work/current authorization, revision, duplicate intent and artifact references; writes state/event/receipt in one checked transaction. Console preview/confirmation and the local-chat caller seam delegate to that API. Immutable journal records exact request, actor/channel/source, confirmation digest, before/after Work, event id, revisions and version. Installed raw transcript/receipt plus native ordering/binding tests establish the admitted behavior. |
| 2. Failure tests prove one repeated effect, stale conflict and refusal without rights; PLAN chooses replay | PASS in executor checks. Original replay conflicts after its first commit; refreshed same-id/same-intent replay returns stored receipt; changed intent at that stage collides. Tests cover no caller, ungranted/revoked rights, schema-forged authority/scope, altered authorization binding including another workspace copy, terminal Work and current scoped receipt-read. Concurrent same/different-id requests at one revision produce one commit and one conflict. The installed terminal trial separately observes original replay/stale conflict and refusal after revocation. |
| 3. DB mutation/event/receipt consistency, reconstructable audit, exact installed version and native/hidden-state evidence | PASS within the tested DB failure model. Tests inject refusal during state update, Event INSERT, receipt INSERT and COMMIT; all retain original DB bytes and matching history, then a valid retry commits once. Explicit v3 migration failure retains v2. A lost CLI reply after commit leaves one readable durable receipt. Journal validation reconstructs current Work through before/after images. Full native checks and installed probes pass on exact 0.3.0; artifacts/raw output retained. File publication is unimplemented and remains Work 4. |

Validation commands and actual scope:

| Command | Result | Raw output |
|---|---|---|
| uv lock --offline; uv sync --locked | Updated project version only; locked dependencies reused. Final locked sync exit 0: 24 packages resolved/audited | docs/work3/evidence/sync-030.txt |
| uv run --locked python -m tools.check | PASS, 51 tests, format/lint/types, 2 architectural contracts, wheel/sdist | docs/work3/evidence/development-check-3.txt |
| uv run --locked python -m tools.probe_install | exit 0, exact c4c7958 wheel; isolated installed import and schema-1 init/status/re-init with unchanged DB | docs/work3/evidence/install-bootstrap-030.txt |
| uv run --locked python -m tools.probe_records --accepted-trial C:/Users/Anton/AppData/Local/Temp/solmax-work1-accept-20260907-a1/retained-trial | exit 0, 0.3.0 installed separately, v1 -> explicit target 2 on a copy, initial records/restarts, old 0.1.0 preserved | docs/work3/evidence/install-records-030.txt; records-trial-030.json |
| uv run --locked python -m tools.probe_mutations --accepted-trial C:/Users/Anton/AppData/Local/Temp/zaratustra-work2-ltyq1qsb | exit 0, real terminal handles and separate installed processes, explicit v2 -> v3 on new copy, exact confirmations and expected refusals | docs/work3/evidence/install-mutations-030.txt; mutation-trial.json; terminal-session.json |
| uv run --locked python -m tools.check --deliver | PASS / exit 0: 51 tests, format/lint/types, 2 architectural contracts, wheel/sdist and report presence; no acceptance truth inferred from the report gate | docs/work3/evidence/deliver-030.txt |

The terminal trial's confirmation inputs were supplied by the executor for the
fictional trial authorized by this development task. They are labeled as such in
terminal-session.json. That file retains tool terminal control sequences and
explicit input markers; install-mutations-030.txt retains subprocess stdout,
noninteractive stderr and exit codes. Interactive stderr/prompt/error text is
preserved in the terminal capture. No successful check depended on a mocked
console, free approval flag or manual DB edit in the installed trial.

Exact retained mutation sequence (one copied accepted Work, no second Process):

| Operation | operation_id | Event | Revision |
|---|---|---|---|
| authorize_work | bcc646b2-4f74-4838-852f-43202acd5264 | 58fa841d-fc00-4fe7-9e74-17889480acc0 | 1 -> 2 |
| set_work_requirements | 86020eab-07db-4744-b4bb-b7af933df9b0 | 4f345190-bf96-43b1-b749-26514d15c27c | 2 -> 3 |
| revoke_work | 377b862e-6889-462f-a1e4-c7120a1ce574 | cf4a8317-b1a6-4071-8760-2a83128aa83e | 3 -> 4 |

workspace_id: 4846e59f-b3f8-4ed1-9bb3-fea22f713b88
original workspace created_at: 2026-09-07T15:17:39.027145Z
Process: bae978a9-a181-4368-be55-b1837fd47747
Work: 56785bef-c147-4236-b12a-cad24845567a
Artifact: ae7eca56-fd16-41ad-b262-2981468b922e
initial Event: b0257ea3-6179-4ac2-95a2-de033bf98078
final DB SHA-256: 8c42aab9da01d270ff8a054122e2ae9bbe004cd70ab66b10927961e85c5409ea

The original quartet retains its identity/creation values. Initial Event remains
revision 1/product_version 0.2.0; Process and Artifact remain revision 1 with no active
file. Current Work/state revision=4, status=ready, authority_scope=none after revoke,
executor_requirements=[reasoning,coding]. There are exactly three mutation Events
and three receipts. Actor is local-console-operator; source_ref identifies each
actual console confirmation, not cryptographic human identity. mutation-trial.json
contains every exact request/confirmation/before/after/receipt value.

Preserved originals were hashed again after all trials:

| Original sample | DB SHA-256, unchanged | Wheel SHA-256, unchanged |
|---|---|---|
| accepted Work 1 / 0.1.0 | ec4fd2c045922578fa1344a5c126c94b0b929215efd57e93b773baf3785ca207 | 4f71d1b2aff54d8680d22e01cb58483681a69969c3c3501667e2bb5aabb9482c |
| executor Work 2 / 0.2.0 | cd8169923aa0836bf6964537f2ea59543a44fffec3d4c4d7c2104ab221759de0 | a50f0f2d195b33a5eac08d9dd8a2479b9863cd029af703341781fb0c63d5d53c |
| binding Work 2 / 0.2.0 | e6e4d430e575e17feca718b1063e6640af09103263848030bbb6d81a72905fe1 | a50f0f2d195b33a5eac08d9dd8a2479b9863cd029af703341781fb0c63d5d53c |

Locators/before evidence: retained-inputs.json; after evidence:
accepted-preservation-after.json. New compatibility trial:
C:/Users/Anton/AppData/Local/Temp/zaratustra-work2-3ix9ert1/.
Originals, earlier copies and evidence remain. No accepted workspace was migrated.
v1/v2 migration source bytes and accepted docs/work1/docs/work2/docs/setup are
unchanged. Every named Direction source still matches the initial sources.json
hashes, captured in direction-preservation.json. No Direction OS mutation/archive
read, product remote, CI/CD/Actions or notification setup occurred.

51 tests consist of 30 retained baseline cases and 21 new mutation/adapter cases.
Baseline tests explicitly target schema 2, use actual current package version for
new initial Events, and move the unsupported-schema fixture 3 -> 4. Their behavioral
assertions remain. No frozen test bytes were identified or edited. Negative damaged
DB fixtures only prove refusal; they never create or repair a passing runtime trial.

Development failures are retained rather than hidden: check-1 stopped on a mypy
variable annotation; check-2 stopped on two probe string lengths; both were fixed
before check-3 passed and implementation commit. A direct pytest executable invocation
could not import the development tools package; using the native python -m pytest
invocation passed 51 tests (development-tests*.txt). No gate exhausted three retries.
Copying generated temporary evidence initially met sandbox read restrictions;
approved access then copied the files and verified all original hashes. The initial
copy attempt's unavailable hashes were not evidence of changed inputs.

## assumptions

The exact accepted plan (SHA-256
4f90d19fc742ab616301b6b4121880f76c75faaeb1f606c8190a84853d8b3e0e), registered CALL and
owner W21 words govern this implementation. PLAN's final decision selects the narrow
Work-only allowlist and DB scope. The earlier conditional W21 discussion remains
historical; it is not a currently pending permission request.

LocalAuthorization is a trusted in-process adapter value, not a serialized identity
credential. Core verifies its exact path/request binding and current Work state.
The local application's Python code and console-access principal are within the
owner-accepted trust boundary. This does not prevent hostile arbitrary same-user
Python code, direct filesystem/DB access, or prove a person's identity. No accounts
or secret credential store was introduced.

Every accepted domain mutation advances the single Work and global state revision
together. The intent fingerprint covers workspace/Work/operation/payload/references/
provenance, excludes the lookup id and expected_revision, and is separate from the
authorization digest over the entire exact request/path. Thus refreshed same-intent
replay can reach duplicate stage without silently changing §5. Original stale replay
conflicts first; current rights/terminal refusal can precede even that conflict.

Receipt-read is scoped and checks current rights before receipt lookup; terminal Work
may read history while rights remain, revocation denies it. records read/history are
owner-local inspection under the existing filesystem boundary, not Work-context APIs.
They are not presented as isolation from the local owner or same-user processes.

Bootstrap remains create-once into an empty store, draft and without grants; a schema-3
store with existing mutation history cannot be reinitialized as a new domain graph.
Only explicit migration adds schema 3. It does not change existing records or rights.
No downgrade, automatic DB repair or fallback to an accepted sample is performed.

Tested failure model: SQLite statement/commit rejection, transaction rollback,
concurrent local requests, authority change after preview, and lost CLI output after
a completed commit. Process-kill/hot-journal recovery, power loss, disk loss and
hostile path replacement are not proved. No stronger guarantee is claimed.
Artifact references are unsupported and rejected at stage 5; the affected projection
set is explicitly empty for this allowlist. Actual publication/rebuild/recovery
must be implemented in Work 4 before dependent operations. No empty-set test is
presented as proof of those future file obligations.

## cuts

No Work 3 done_when was removed. The bounded operations supply the admitted mutation
protocol while preserving sequential Works. Handoff/file-stdin import, content
publication/projections, Work context, submit_result/next Work, the clean chat and
full scenario remain Works 4–8 and are not implemented or claimed.

No real Process, second full Process, permanent personal workspace, M1+, MCP,
independent external install/upgrade, full move, account/login or paid service.
CI/CD, Actions, notifications, external setup/test pushes and publication remain
excluded under owner-ack:solmax-zaratustra-work1-no-automation-20260907 and
owner-ack:solmax-zaratustra-local-setup-no-automation-20260907.
No direct DB/state Markdown repair, Direction OS/old-repository write, secret/archive
read, remote/account change or external/irreversible action.

W19–W27 are retained by name; PLAN owns remaining dependent decisions:

| ID | Work 3 disposition / remaining obligation and rewrites |
|---|---|
| W19 | Literal order, original stale replay conflict, refreshed duplicate receipt, collision, terminal refusal and current-rights disclosure selected/tested. Result/next effect remains PLAN before Works 5/7. rewrites: importer, receipts, linkage, failure tests/migrations; cheap reversal unproved. |
| W20 | DB state/event/receipt atomicity and tested lost-reply behavior measured. PLAN before Work 4/7: publication, orphan/recovery/rebuild, late artifact availability and Result continuation. rewrites: durable references, recovery/evidence/migrations; DB checks do not prove file durability. |
| W21 | Owner-selected local console boundary implemented; actual current/revoked rights, exact request/path binding and scoped receipt-read tested. Trusted local-chat library seam avoids repeated identity confirmation after actual permission; no file/model self-grant. PLAN before Works 5/6/7 must bind the actual importer/context consumer. rewrites: adapters/import/permissions; the owner decision is not runtime acceptance. |
| W22 | One transaction/snapshot; global revision covers every admitted rights/status/requirements change, preventing stale target-only updates. PLAN before Work 4/6: decisions/membership/artifact dependencies, scope/freshness/budget and delivered manifest. rewrites: snapshot/context/contracts/tests; none of those duties is cut. |
| W23 | No clean-chat proof. PLAN protocol before Work 6/8; exact delivered input and actual separate response by five facts in Work 8. rewrites: delivery/demo; unprovable clean surface remains a blocker. |
| W24 | Explicit v3 migration, version-1 typed requests, UUID identity, canonical JSON/SHA-256, UTC timestamps, separate expected revision, transaction/BUSY mechanics selected. Future recovery/cleanup before dependencies; semantics return W19–W22. rewrites: mechanics/tests/migrations. |
| W25 | One accepted fictional graph per new copied workspace, negative foreign-id/path binding and retained link-integrity cases. No second full Process; these are not Work-context isolation proof. PLAN fixtures before Works 5/6/8; rewrites: fixtures/tests/demo. |
| W26 | Actual local bases/branch/no remote, separately installed 0.3.0, preserved 0.1.0/0.2.0 and exact hashes verified. Permanent folder, hosting and external independent install-upgrade remain future admissions. rewrites: package/layout/docs; reassess with outside consumers. |
| W27 | Public Core mutation/data/receipt seams available to future E1/E2/E3/E6/E8/E9/E10/E11 consumers; no incoming M1+ prerequisite. E4/E5/E7/E12 receive no invented direct M0 API. Full consumer contracts stay PLAN at their admissions. rewrites: Core/data and consumer migrations; cheap replacement unproved. |

## cost

One executor; no subagents or independent reviewer required by PROBA v36 for this
Work. Approximately 60–90 minutes of implementation/check/report work after the
W21 response, plus the earlier approximately 25–35 minute source/PLAN/blocker leg;
estimates, not timed billing. The resulting increment fits the half-focus-day
calibration. No new deadline, dependency, expense or external service.
Exact token/subscription cost unavailable; existing managed tools/subscriptions reused.

Two full development check failures were corrected; the next full check passed.
Focused feedback did not substitute for full delivery. All three installed probes
passed on c4c7958. Routine sandbox escalations for uv/cache, Git commits and reading
generated temporary receipts were approved; no required tool or approval remains
blocked. Local checks are engineering evidence, not binding Direction G5.

## manual-acceptance

Owner decision W21: accepted explicitly, exact words in
docs/work3/OWNER-DECISION-20260908.md.
Owner Work 3 runtime acceptance: not performed or inferred.
Binding fresh physical G5 for Work 3: not performed in this authoring session.
Work 8 owner demonstration remains mandatory at that later admission.

To read the exact measured installed state in another terminal:

~~~powershell
& 'C:/Users/Anton/AppData/Local/Temp/zaratustra-work3-gnt5ksg0/venv/Scripts/zara.exe' --version
& 'C:/Users/Anton/AppData/Local/Temp/zaratustra-work3-gnt5ksg0/venv/Scripts/zara.exe' records read 'C:/Users/Anton/AppData/Local/Temp/zaratustra-work3-gnt5ksg0/workspace'
& 'C:/Users/Anton/AppData/Local/Temp/zaratustra-work3-gnt5ksg0/venv/Scripts/zara.exe' history 'C:/Users/Anton/AppData/Local/Temp/zaratustra-work3-gnt5ksg0/workspace'
~~~

Expected persisted facts are the exact ids/revisions/history above and in
mutation-trial.json. The trial ends with rights revoked deliberately. It is not a
permanent personal workspace. For a new interactive run use docs/work3/INSTALL.md;
the probe creates another copy and prompts for each exact fictional operation.
Keep measured original trials unchanged. No manual DB edit is part of the procedure.

## next

next: solmax
HOME: evaluate this full Product RESULT, implementation c4c7958, exact installed
artifacts/raw evidence, owner W21 decision and all three original Work 3 done_when.
The required close route remains binding fresh physical G5 under Direction rules.
This authoring session does not consume/close the CALL, T2 or M0, infer owner runtime
PASS, issue a successor Direction CALL or authorize Work 4–8. W19–W27 and retained
samples remain attached to their named future decision points.

END_OF_FILE: RESULT.md
