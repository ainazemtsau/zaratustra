# Product RESULT — Work 7, HOME solmax

call: c-solmax-zaratustra-m0-result-20260908-work7
mode: PROBA; engineering_contract: 36
product: C:/projects/zaratustra/_scratch/work7-result
branch: codex/work7-result
base: 2fa3111666139eef3ae699319444809fce563ead
plan_commit: 69829a9458253d0ae7ba6912f276612c0b22c799
implementation_commit: 90f35f6251a5dc1511e9ac94e5f5dee11628bfa0
final_source_candidate: 5866a48c5f9d0f492ad55723120366ffe8f08921
version: 0.7.0; schema: 6; default explicit migration target: 4 (unchanged)

## outcome

REPORT: Work 7 implementation and executor evidence returned HOME.
submit_result commits a completed source Work, immutable Result, mutation event,
receipt and exactly one ready next Work in one transaction. read_result recovers
the accepted link by original operation id after restart or lost response.
open_work delivers the next Work's exact current context with historical grounds.
This is Product engineering evidence; T6/CALL/M0 remain Direction responsibilities.

| CALL done_when | Actual evidence and limit |
|---|---|
| 1. Result, mutation, receipt and next Work are saved and recoverable | Installed console submit commits revision 11 -> 12. Source completion_id equals operation_id; immutable Result/event/receipt name the next Work. New process and restored installed runtime recover the same Result and next id. Raw result.json, console-submit.stdout, final-build.json, restore-verification.json. |
| 2. PLAN W19/W20 defines the effect and prevents duplicate/lost continuation | PLAN committed before implementation. Native and installed checks cover terminal replay/new id, stale/collision/current authority, rollback/exact retry, post-commit lost response, projection failure, byte loss/repair and restart. Unknown outcome uses discovery, never a new id or reopening. |
| 3. Next package preserves decision, basis, effective revision, result and next step | Exact 20873-byte CLI package contains incoming Result/source images, both accepted decisions and their historical revisions, two exact versioned grounds, and the explicitly confirmed next goal/criteria/scope. CLI/library/restore bytes match. Understanding these five facts in an actual separate clean chat remains T7/Work8. |

## evidence

Authority was checked against issuing Direction main
3b9db6e2460dcf271e95b3937f4d123dbd9e2c04, authenticated remote main at start.
PLAN records the required architecture/contract/Work6 close inputs; CALL.md retains
the complete issued task. Work6 binding G5 is prior evidence for unchanged claims,
not a verification of this new Result behavior. No Direction state was written.

Contract: docs/work7/PLAN.md. Exact fixture permission: OWNER-FIXTURE.md in that
directory. Runnable installation, reproduction and expected observations:
docs/work7/INSTALL.md. All raw paths below are in docs/work7/evidence/.
Base-to-source diff: implementation.patch. Final evidence/docs commit is returned
in the HOME message; no self-referential commit id is invented in this file.

Native full tools.check before the narrow CLI repair passed 139 tests plus build,
hygiene, ruff, mypy and two import boundaries (native-fourth.*). The encoding
repair added a child-process regression; focused Result tests then passed 21
cases. Final full --deliver PASS: 140 tests in 29.52s, build, hygiene, ruff, mypy,
two import boundaries and report structure. Raw: native-deliver.json/stdout/stderr;
exact command and duration: docs/work7/DELIVERY.md. Earlier failed native runs are retained as
diagnostics; they are not PASS evidence and no old test was rewritten.

Installed Python 3.13.7 / SQLite 3.50.4 / Pydantic 2.13.5. Final wheel and 19
installed Python files equal the source candidate; -I runs use unrelated-cwd
without source checkout on sys.path. See installed-source-final.json. Initial
manifest.json, installed-source.json and first six console runs refer to
implementation 90f35f6, before the output-only repair. final-build.json,
locale-after.*, console-final-discover.*, installed-extra.json and restored
runtime identify final source 5866a48. The repaired wheel was installed into the
same explicitly selected new trial without changing its main DB.

Seven actual executor console confirmations were performed: submit/discover/next,
expected terminal replay/stale/budget refusal, then final repaired discovery.
Prompt and terminal-session raw are retained. Additional Core fault injections
explicitly simulate prior-permission local-chat authority; they are not actual
owner runtime acceptance. Fault workspaces remain labeled negative-copies.

| Installed evidence | Observation |
|---|---|
| console-checks.json and console-*.stdout | Main submit/discovery/next succeed; terminal replay, stale and budget return exit 1 with empty stdout. |
| hidden-checks.json, exercise-receipt.json | 14 groups: terminal original/new id, stale, collision, missing authority, lost response, projection failure, missing/corrupt/late-lost bytes, exact budget boundary, foreign Process/ref and revoked consumer. |
| installed-extra.json, installed_extra-source.txt | Five additional groups: SQLite write-denial rollback preserves DB then exact same-id retry; missing/corrupt exact repairs preserve Result/link and quarantine; registered but ungranted historical version refuses; a separate OS process discovers committed lost-response Result and same next context. |
| locale-before.*, locale-after.*, console-final-discover.* | Actual new result-read command fails under ASCII stdout before repair, succeeds after repair with all decoded Russian values retained. Final actual console output equals locale-after.stdout. |
| restore-verification.json and restore-* raw | PowerShell Expand-Archive creates a new selected copy; offline installed final wheel reproduces Result and exact context. 149 files match and 136 directories exist after reads. |
| preservation-before.json, preservation-after.json | Accepted Work5/6 refs, tracked bytes, retained trial files/directories and selected Direction authority bytes remain unchanged. |

The first additional restart diagnostic recovered data but failed printing its
summary under cp1252; lost-reply-restart.json preserves that failure. Its corrected
driver writes explicit UTF-8 and lost-reply-restart-final.json records success.
OUTPUT-REPAIR.md gives the discovered class, repair, regression and sibling sweep.
Legacy owner-local records/history text output under restrictive encodings remains
an explicit HOME:work7-locale-output-audit follow-up, outside this Result delta.

Trial: C:/Users/Anton/AppData/Local/Temp/zaratustra-work7-m8i5i307.
Runtime: venv; selected data: workspace. Main DB schema6/revision12.
Actual restored trial: C:/Users/Anton/AppData/Local/Temp/zaratustra-work7-restore-0dy2qb3o.
Negative copies are diagnostics, never a main or restore base.

| Identity | Exact value |
|---|---|
| workspace | 4846e59f-b3f8-4ed1-9bb3-fea22f713b88 |
| Process | bae978a9-a181-4368-be55-b1837fd47747 |
| source Work, now done | 56785bef-c147-4236-b12a-cad24845567a |
| Result operation / completion id | 9179d4f8-d868-49c0-8ec8-3df7078bffc8 |
| mutation event | a23d88b5-132a-434c-b6de-c339c48130f1 |
| next Work, ready | 09154bbb-34e0-4917-ad85-74cbaee0824d |
| next Artifact, declared | 7f72c737-0ed3-420d-bc82-dfe69996cdb2 |

| Exact artifact | SHA-256 / measurement |
|---|---|
| final wheel zaratustra-0.7.0-py3-none-any.whl, retained in ZIP | dada5424fdf899c7d78d62b97f7acbd9edece35bc2c322e65e877b3bb6db8b84 |
| main workspace/.zara/state.sqlite3 | 8ade9179887bcd3fe5a6f022e2f63d66b8fd51ce62dffc6ddd9c25aecb10979c |
| exact request.json | ad2a030fd6bc1c5c730adc3034b4379e617327f65c4d9a5e026ee612e988a5a9 |
| result.json | 5339e129f6855b10d0f530257b22df08b1df3b89f3eff7c6fcaac0e72db4df11 |
| console-next.stdout = context-library.json = restore-context.stdout | f9549bbbfd83eed752dae510c2f91db06217ff130673558c0643af5744fe1894; 20873 bytes including LF |
| retained-trial.zip | 90acb543e44959949ea90a94a004528598fcc75b70bb58a6f2f6f21079bcdd2f; 149 files, 136 directories |
| accepted Work6 retained-trial.zip, unchanged | 1657d3a559ba1275ea010b5d83ff0cb818ba26fa74ab195cc86f8218ac57d539; 75 files, 72 directories |
| accepted Work5 retained-trial-v2.zip, unchanged | fdb39d39441f9e739e2d6ec17391ad7500a8d86284a79b186df073088487bb51 |

ContextQuery exact bytes: query.json; discovery query: receipt-query.json.
Manifest: context-manifest.json and final-build.json. Full budget is 20873/65536
UTF-8 bytes including envelope, source values, manifest and LF; eight sources:
Process, current Work, declared Artifact, incoming Result, two acceptances and two
versioned content objects. Handoff source revisions9/10 remain historical;
acceptance revisions10/11 and submitted source revision11 differ from current
global/Work/authority revision12. Process revision1 and new Artifact revision1
remain explicit. No human effort budget conversion, truncation or silent increase.
The old schema5 context reproduced exactly (12320 bytes, SHA-256
438bf8af803b20763c9e904097c7f5f250e2b06f34928720535d7e903604df85)
before explicit migration6 on the new copy.

Freshness is only at full final revalidation, not a lease for later work. Incoming
historical grants are finite exact versions, not arbitrary ancestor access or
acceptance of the next goal. Current consumer revocation refuses open/discovery
as applicable. DB/projection/receipt presence never proves current content bytes.

### W19–W27 decisions, residual answerers and rewrite exposure

| ID | Decision / answerer and moment | rewrites |
|---|---|---|
| W19 | Product PLAN before submit: one atomic Result/completion/next effect, terminal refusal, original-id discovery. Exact fictional content owner-confirmed; real owner content goes HOME before use. | Journal, importer, receipts, links, failure tests; cheap reversal unproved. |
| W20 | Product PLAN before writes: prior published bytes, complete reference validation, transaction, post-commit discovery, exact repair/restore. | Durable refs, recovery, evidence, migration. |
| W21 | Product PLAN before consumer: exact request/path/content/next-rights confirmation and current scope. Owner before any real new rights/content. | Permissions, adapters, consumer boundaries; trust decision is not runtime PASS. |
| W22 | Product PLAN before next context: per-Work journal, conservative global invalidation, all acceptances and finite inherited closure; two-pass full bytes and full wire budget. | Snapshot/context contracts, tests, migration; no freshness/scope/budget cut. |
| W23 | Product PLAN before package: exact input/output retained. Product PLAN/owner at T7 decide actual separate clean-chat delivery and five-fact demonstration. | Delivery/demo and possible Work8 repeat; clean-chat evidence still absent. |
| W24 | Product PLAN before implementation: request v4, explicit schema6, local SQLite transaction/BUSY, old serializers and migration defaults preserved. | Local mechanics/tests/migration; semantic change returns W19–W22. |
| W25 | Product PLAN before fixtures: only new copies of one fictional accepted graph, failure/replay/recovery/authority/scope/budget. Owner's exact fixture words retained; T7 demo later. | Fixtures/tests/demo, no second full Process. |
| W26 | Product PLAN before start: isolated accepted-base checkout and installed trial, prior evidence preserved. Owner before permanent location/hosting/independent external upgrade. | Package/layout/docs; no new external rights. |
| W27 | Product PLAN before public consumer: only Result/next/context M0 seams. Future consumer PLAN at separate admission answers E1–E12; E4/E5/E7/E12 have no invented direct M0 API. | Public Core/data/future migrations; cheap replacement unproved; M1+ not prerequisite. |

## assumptions

The owner's “тогда подтверждаю” confirms only the exact fictional NextWork fixture
in OWNER-FIXTURE.md. Its goal, comparison criterion, Fictional observatory boundary,
One short local session budget and metadata-only rights are in request.json.
No real task content, publication right or new identity is inferred. Existing W21
local-console/prior-permission trust applies; hostile same-OS-user defense and
power-loss/disk-loss guarantees are not added to the accepted local SQLite model.

## cuts

No CALL done_when was dropped. Actual clean-chat understanding and owner demo are
explicit T7/Work8 work, not silently substituted by this manifest. No automatic
executor/Work8, M1+, MCP/transport, memory/retrieval/router/frontend/autonomy,
external install/upgrade, Product remote/publication, CI/CD/Actions/notifications,
expenses or live Direction/archive writes. Released migrations1–5 and prior
Works' acceptance artifacts/tests were not rewritten. New schema6 is opt-in on
new selected copies only; init1 and default migrate4 remain.

## cost

One local engineering session, three source/plan commits followed by evidence/docs
delivery; new isolated checkout, installed trial and restore, no external spend.
Native full check initially failed, then passed on the third retry; raw native
first/second/third/fourth outputs remain. The later narrow Windows-output repair
has its own actual RED/GREEN reproduction and final full delivery gate. No frozen
pair, separate test-author or subagent review is claimed. Account token/currency
cost was not measured; no new owner deadline or budget was promised.

## manual-acceptance

Owner fixture permission exists; owner runtime acceptance does not. Seven console
confirmations above were executor actions on the authorized fictional copy.
Binding fresh physical G5 of this exact candidate has NOT been performed here.
This Product RESULT cannot close T6, its open CALL or M0. Five-fact actual clean
chat and demonstration to the owner have NOT happened and Work8 has NOT started.

## next

next: solmax
HOME receives this complete Product RESULT, source candidate and retained raw
evidence. Direction arranges the required fresh physical G5 against all three
claims and decides T6 close/any later Work8 admission. No Direction successor is
issued by this Product session. Concrete additional follow-up, not a CALL:
HOME:work7-locale-output-audit in docs/work7/OUTPUT-REPAIR.md.

END_OF_FILE: RESULT.md
