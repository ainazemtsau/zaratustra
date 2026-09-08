# Product RESULT — Zaratustra Work 2

call: c-solmax-zaratustra-m0-bootstrap-20260907-work2
engineering_contract: 36
mode: PROBA
repo: C:/projects/zaratustra
direction: solmax
node: g-zara-m0-continuity
task: t-zara-m0-foundation

## outcome

WORK2_IMPLEMENTED_AND_LOCALLY_VERIFIED / REPORT HOME.
Version 0.2.0 saves initial Process, draft Work, declared Artifact and Event with
revisions in a separate workspace and reads the same records in later installed
processes. Explicit migration v2 preserves the accepted v1 bootstrap metadata.

This is the minimal Work 2 record layer: one initial quartet; each record revision=1,
state_revision advances 0→1. Work has no authority and cannot execute. Artifact has
no active file. There is no update/replay/Handoff/content-publication protocol.
The full W19–W27 decision/disposition record is docs/work2/RECORDS.md.

Executor's local checks passed. Owner runtime acceptance and binding fresh-session
Direction G5 have not occurred in this session. Product evidence does not close the
Direction CALL, T1 or M0. Work 3–8 remain unimplemented and require new admission.

## evidence

product_basis: bc6f053ee62db9a5b711594e73933f1a9cdbf6cf
accepted_work1_implementation: bbeae5c17d53e7f24dca22bbd9403cd39c19d094
implementation_commit: ce8ae68cf555f05864c9dd6b82cfbfd9babe61b1
branch: codex/work2-core-records
version: 0.2.0
Implementation diff: 17 files, 1057 insertions, 60 deletions.
Exact diff: git diff bc6f053ee62db9a5b711594e73933f1a9cdbf6cf ce8ae68cf555f05864c9dd6b82cfbfd9babe61b1
Raw commit/stat: docs/work2/evidence/implementation.txt.
Full implementation patch: docs/work2/evidence/implementation.patch.
The following report commit contains only RESULT.md and docs/work2/evidence;
it does not change the measured source, package metadata, instructions or tests.
The previous full Product RESULT remains at the accepted product_basis commit.

wheel: dist/zaratustra-0.2.0-py3-none-any.whl
wheel_sha256: a50f0f2d195b33a5eac08d9dd8a2479b9863cd029af703341781fb0c63d5d53c
Observed installed runtime: Python 3.13.7, SQLite 3.50.4, Pydantic 2.13.5, Windows.
Dependencies retained their locked versions; uv.lock changed only product version.

| CALL done_when | Measured result and evidence |
|---|---|
| 1. Minimal Process/Work/Artifact/Event and revisions survive between installed launches; evidence binds version/data. | PASS in executor's local run. Core records.py validates/stores the four typed records and their links. Installed 0.2.0 records create and records read run as separate OS processes from an unrelated cwd; complete JSON is equal, including UUIDs, revisions, Work fields and Event product_version. The SQLite SHA-256 remains equal after rereads, repeat-create refusal, init, repeat-migrate and old-version refusal. Full raw install-records.txt and retained-trial.json contain exact observed values. |
| 2. Work 1 installation/init preserved; explicit migration preserves accepted bootstrap; native checks and hidden-state tests pass. | PASS in executor's local run. Unchanged released migrations.py creates schema 1; migrate explicitly adds schema 2 in one transaction. The trial upgrades only a copy of the accepted workspace. workspace_id/created_at and v1 history are preserved; original 0.1.0 wheel/DB hashes unchanged and original executable still reads its original workspace. A second fresh init→migrate→create→read also passes. Full native build/hygiene/types/2 boundaries/30 tests pass; original installed bootstrap probe passes for 0.2.0. |
| 3. Full Product RESULT, commits/diff/artifacts/raw installed evidence, all report fields and W19–W27; no later closure/automation. | This report, RECORDS.md, INSTALL.md, implementation patch and complete raw outputs carry the named evidence, decisions and limits. Native deliver validates report structure plus standard checks, not acceptance truth. All nine dispositions remain explicit below and in RECORDS.md. Work 3–8/T1/M0 and CI/CD/Actions/notifications retain their boundaries. |

Commands run on the committed implementation:

| Command | Outcome | Raw output |
|---|---|---|
| uv sync --locked | exit 0 | docs/work2/evidence/sync.txt |
| uv run --locked python -m tools.check | exit 0; 30 tests, types/format/lint, 2 boundaries kept, wheel/sdist | docs/work2/evidence/check.txt |
| uv run --locked python -m tools.probe_install | exit 0; installed 0.2.0 init/status/re-init, equal schema-1 DB bytes | docs/work2/evidence/install-bootstrap.txt |
| uv run --locked python -m tools.probe_records --accepted-trial C:/Users/Anton/AppData/Local/Temp/solmax-work1-accept-20260907-a1/retained-trial | exit 0; copied-baseline and new-empty-workspace scenarios, retained installation | docs/work2/evidence/install-records.txt |
| uv run --locked python -m tools.check --deliver | exit 0; 30 tests, native checks/build and report structure PASS | docs/work2/evidence/deliver.txt |

Exact retained upgraded-copy observations:

- workspace_id: 4846e59f-b3f8-4ed1-9bb3-fea22f713b88
- original created_at retained: 2026-09-07T15:17:39.027145Z
- schema: 1→2; state_revision: 0→1; all object revisions: 1
- Process: 79d30aa9-4ccd-4940-ac7c-cb3d7ce5e323, Fictional observatory
- Work: 945545ed-3c7d-46d0-80df-6314c08916a3, Describe an imaginary moon
- Artifact: 54f63a72-759c-470c-9ba5-c08d47a25066, Observation draft; active_version=null
- Event: 8d160b2c-69e4-48d1-984c-e55dec06bfa7; initial_records_created; product_version=0.2.0
- record created_at: 2026-09-08T03:37:06.194216Z
- DB hash after create and after repeat reads/refusals: cd8169923aa0836bf6964537f2ea59543a44fffec3d4c4d7c2104ab221759de0

The accepted original remains at
C:/Users/Anton/AppData/Local/Temp/solmax-work1-accept-20260907-a1/retained-trial/.
Its original DB hash remains ec4fd2c045922578fa1344a5c126c94b0b929215efd57e93b773baf3785ca207;
its original 0.1.0 wheel hash remains 4f71d1b2aff54d8680d22e01cb58483681a69969c3c3501667e2bb5aabb9482c.
The original executable reports 0.1.0 and reads that original schema-1 workspace.
It refuses the migrated copy without changing it. The original was never migrated.

30 tests comprise 20 prior bootstrap/development checks and 10 new record/migration
cases. The newer-schema refusal fixture changed from version 2 to 3 because 2 is now
supported; its refusal assertion remains. Tests cover complete persisted fields and
links, no silent migration, no self-grant fields, repeat preservation, corrupt-record
refusal and transaction rollback at migration insertion and final Event insertion.
Invalid DB fixtures are isolated fault cases, never manual repairs of a passing trial.
No custom source scanner is used as product behavior evidence.

One initial full development run failed only on two test-helper mypy annotations;
they were corrected before implementation commit. The next full run, committed run
and both installed probes passed. No gate exhausted the three-attempt retry budget.
review: n/a — PROBA v36; no mandatory product review artifact or independent test author.
close_evidence: executor's in-session checks only; binding fresh-session G5 not performed.

## assumptions

The exact Work 2 choices conform to plan §§3–7,26–29,41 at SHA-256
4f90d19fc742ab616301b6b4121880f76c75faaeb1f606c8190a84853d8b3e0e.
The comparison and sources are in docs/work2/RECORDS.md. Applied existing delegation:
owner-ack:solmax-plan-conforming-20260907 — «В принципе все вот эти моменты авто
подтверждать, если не идет какое-то рассогласование плана». These recorded words
permit plan-conforming decisions; they do not establish owner runtime success.

Initial local creation is a bounded bootstrap before an executable Work exists,
not an imported mutation or a grant. CLI delegates to the one Core domain write
entry; it accepts no actor/approved/authority/id/revision fields. The saved local
invocation provenance does not claim the human personally performed that invocation.
Current reads use local filesystem access, not future Work-scoped context authority.

Artifact is an initial declaration with no bytes/hash/active reference. Work is draft
and authority_scope=none, with empty context/dependencies. Budget is saved text, not
enforced execution. Object/global revisions describe initial state only; updates,
revision advancement/history and mutation receipts remain Work 3 dependencies.
No duplicate-first choice or permission bypass has been selected.

A single SQL snapshot validates all four initial records. Fault rollback is shown,
but process-kill/power-loss, hostile same-user races, full recovery, file publication
and projection rebuild are not proved. No downgrade is implemented. Work 1's partial
filesystem-init retention behavior remains. Windows is observed; other OSs untested.

W19–W27 disposition; full sources, timing and reversal costs in RECORDS.md:

| ID | Work 2 disposition / remaining PLAN obligation |
|---|---|
| W19 | Initial revisions and create-once guard selected. Replay/collision/terminal/receipt-read and Result-next effect remain PLAN before Work 3/5/7. Literal §5 stays authoritative. rewrites: importer, receipts, linkage, tests/migrations; cheap reversal unproved. |
| W20 | Explicit DB migration and initial-record transaction measured; Artifact has no active content. Publication/commit visibility/orphans/recovery/rebuild remain PLAN before dependent Work 3/4/7. rewrites: references, recovery/evidence/migrations. |
| W21 | First Work is a draft with no rights; explicit local bootstrap, no self-authorizing input. Trusted caller/receipt binding, current/revoked rights, scope and receipt disclosure remain PLAN before Work 3/5/6/7. rewrites: trust adapter and mutation/read permission checks. |
| W22 | Consistent whole initial graph snapshot and initial global/object revisions selected. Dependent revisions for decisions/rights/membership, context scope/budget/manifest remain PLAN before dependencies in Work 3/4/6. rewrites: snapshot/context contracts and checks; no freshness cut. |
| W23 | No separate-clean-chat claim. PLAN protocol before Work 6/8 and exact delivered input/real response in Work 8. rewrites: delivery/demo; inaccessible clean surface is a blocker. |
| W24 | v2 schema, immutable typed values, UUID/time, initial revisions, CLI, transaction/BUSY and retained trial resolved locally. Later operation/recovery formats remain PLAN. rewrites: mechanics/tests; semantics return W19–W22. |
| W25 | Minimal fictional observatory fixture and invalid foreign-id fixture; no full second Process. Actual foreign-context exclusion remains PLAN before Work 5/6/8. rewrites: fixtures/checks/demo. |
| W26 | Actual repo/basis/branch/no-remote verified; version 0.2.0 installed separately, 0.1.0 preserved. Permanent folder, public hosting and external independent install/upgrade remain future decisions. rewrites: package/layout/docs; reassess after outside dependency. |
| W27 | Only initial Core data/read seams implemented. E1/E2/E3/E6/E8/E9/E10/E11 future contracts remain PLAN per consumer; E4/E5/E7/E12 receive no invented direct M0 API. No incoming M1 prerequisite. rewrites: public data/consumer migrations; cheap replacement unproved. |

## cuts

Only the admitted minimal Work 2 records/revisions increment inside T1. No required
Work 2 done_when was dropped. Work 3 mutation/expected_revision/operation_id/receipt,
Work 4 versioned file publication/projections, Work 5–8, M1+, MCP, real Process,
permanent personal workspace, independent install/upgrade and full move remain out.
No arbitrary SQL/Markdown edit was used to create or repair acceptance data.

CI/CD, GitHub Actions, notifications, setup and test pushes remain cut by
owner-ack:solmax-zaratustra-work1-no-automation-20260907 and
owner-ack:solmax-zaratustra-local-setup-no-automation-20260907;
product receipt: docs/setup/OWNER-DECISION-20260907.md.
No remote/account/publication, new expense or external rights. No Direction OS
writes, old-repository changes or archive reads. The product issues no Direction CALL.

## cost

One single-agent Work 2 leg; approximately 35–45 minutes including source/contract
reading, implementation, checks and report (estimate, not a timed billing record).
This fits the half-focus-day calibration. Existing managed uv/Python and pinned
packages were reused; no new dependencies or paid services. Exact token/subscription
cost unavailable. Local sandbox escalations for Git writes, uv/cache/install execution
and copying the generated temporary receipt were approved; no tool remains blocked.

## manual-acceptance

Owner-performed runtime acceptance: pending. The installed executor trial remains at
C:/Users/Anton/AppData/Local/Temp/zaratustra-work2-8cv9m8jt/ with wheel, environment,
requirements, migrated-copy workspace, fresh-workspace and receipt.json.
It is a disposable fictional trial, not the owner's permanent workspace.

For a second-terminal read of the exact measured state:

```powershell
& 'C:/Users/Anton/AppData/Local/Temp/zaratustra-work2-8cv9m8jt/venv/Scripts/zara.exe' --version
& 'C:/Users/Anton/AppData/Local/Temp/zaratustra-work2-8cv9m8jt/venv/Scripts/zara.exe' records read 'C:/Users/Anton/AppData/Local/Temp/zaratustra-work2-8cv9m8jt/workspace'
```

Expect version 0.2.0 and the exact four ids/fields/revisions listed above and fully
saved in docs/work2/evidence/retained-trial.json. Independent recreation commands
are in docs/work2/INSTALL.md. No manual DB repair is part of that procedure.
The report offers a concrete owner trial but does not label it passed by the owner.
This is not the Work 8 full M0 demonstration or an independent participant's proof.

## next

next: solmax
HOME: return this complete Product RESULT and its committed evidence for Work 2
acceptance, applicability of previous setup/Work 1 receipts to the same claims/inputs,
and the required close evidence for all T1 before any Work 3 admission.
The existing T1 close route remains binding fresh-session G5, or light only if each
line is actually eligible and re-derived under work rules. This authoring session
supplies no binding G5 and does not decide Direction closure. Work 3–8, T1 and M0
remain open. Only Direction consumes its CALL or issues a successor.

END_OF_FILE: RESULT.md
