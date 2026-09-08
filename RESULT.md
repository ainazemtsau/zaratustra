# Work 4 — Product REPORT HOME

## outcome

REPORT: Work 4/T3 implemented as version 0.4.0, with local engineering PASS for
the three admitted done_when in the declared failure model. Versioned publication,
verified content read/repair and DB-derived rebuild retain the single Mutation API
and accepted local trust boundary. This report does not close T3/M0, assert owner
runtime PASS or binding fresh G5. Work 5 has not started.

call: c-solmax-zaratustra-m0-artifacts-20260908-work4
mode: PROBA; engineering_contract: 36
actual_worktree: C:/my_global_workflow/68ce/zaratustra
actual_branch: codex/work4-artifacts-projections
accepted_product_basis: 11b4b95d0f696c63e3ae4d56cb8fb4b748cd933d
implementation_commit: 2100775adfd78ad83a3ff615f9d9e4eeec32eb5b
direction_admission: e223143d9fc90127ae3e198b96f57d49254a171b
product_remote: none

The full Work 4 CALL and closed T2 were observed together in committed Direction
origin/main before product changes. The initially clean detached worktree was
based on the required HEAD; its dedicated branch was then created. Direction was
only read. The original Product checkout and accepted runtime samples were preserved.
Full CALL: docs/work4/CALL.md; technical decisions: docs/work4/PLAN.md.
Diff/commit evidence: docs/work4/evidence/implementation.patch and implementation.txt.
Subsequent report/evidence and locator commits are documentation only; executable
source stays exactly implementation_commit. Final HEAD is available via git
rev-parse HEAD and the HOME locator. Prior full Work 3 RESULT remains at the accepted
basis commit, SHA-256 cb6cd0518be0fc67092e478cd1917d9718d370f18090fd1f3ae5732fa371a7f4.

## evidence

| Original CALL done_when | Actual engineering result |
|---|---|
| 1. Versioned/immutable artifacts have verifiable SHA-256 and consistent registration/active revision in §4 order; W20 publication/recovery boundary defined | PASS in executor checks. Complete staged bytes are flushed/fsynced and hashed, then published without replacing an immutable name, before DB registration. Descriptor/active Artifact revision, Work/global revision, event and receipt commit together. Explicit schema 4 preserves v1/v2/v3 migrations and old records/history. Installed versions remain separately readable with retained ids/hashes/receipts. PLAN defines orphans, retry, exact repair and physical availability. |
| 2. Read-only projections show provenance and rebuild from authoritative state; failure is no second change/truth | PASS in executor checks. overview.md contains generated_from_revision/generated_at, records, version metadata and provenance. Deterministic rebuild reads the latest DB under the shared writer lock and atomically replaces the overview without DB writes. Delayed rebuild cannot overwrite newer state. Missing/stale/changed status is explicit; missing directories recover too. Post-commit failure returns the saved receipt and rebuild_required, CLI exit 2. Explicit rebuild makes no new event/revision. |
| 3. Publication/commit/rebuild and unavailable/changed-content checks establish consistency without manual DB/state repair; exact installed version/artifacts/raw native evidence retained | PASS within the stated local model. Native failures cover flush/publication, version registration, Artifact/Work/global writes, event/receipt/COMMIT, interrupted repair and v4 migration. Rollback preserves DB bytes; same-id retry reuses a verified orphan and commits once. Reads refuse missing/modified bytes; scoped foreign/missing references and revoked/terminal rights refuse. Installed 0.4.0 exercises real console delivery, two versions, content refusal/repair, COMMIT failure and committed rebuild recovery on new copies. |

Exact artifact and runtime locators:

| Item | Value |
|---|---|
| Version/schema | 0.4.0 / explicit schema 4; init remains schema 1 |
| Built wheel | dist/zaratustra-0.4.0-py3-none-any.whl |
| Retained wheel | C:/Users/Anton/AppData/Local/Temp/zaratustra-work4-viai92mt/zaratustra-0.4.0-py3-none-any.whl |
| Wheel SHA-256 | a1fb2df9ed33d5c5fb8e33cc484fd9425e7cd9e17701c535696af8025f07585f |
| installed_command | C:/Users/Anton/AppData/Local/Temp/zaratustra-work4-viai92mt/venv/Scripts/zara.exe |
| installed_workspace | C:/Users/Anton/AppData/Local/Temp/zaratustra-work4-viai92mt/workspace |
| Fault copy | C:/Users/Anton/AppData/Local/Temp/zaratustra-work4-viai92mt/fault-workspace |
| Main DB SHA-256 | bec53e48c79ccfc7e83a72a1439feacf759b48cad9a621d10cd1fa508def77a0 |
| Fault DB SHA-256 | 625b9543287db44a047ea0ab0359fce8b649b2afe9cf112228b774268635699d0 |
| Runtime | Windows; managed CPython 3.13.7; SQLite 3.50.4; Pydantic 2.13.5 |
| Backup | docs/work4/evidence/retained-trial.zip |
| Backup SHA-256 | 1cc89ce63d6b6ff7e73699257db7dfbf80a6025076edad056cbfa3fc0f856f82 |

All 14 installed package .py files equal the exact built wheel and implementation
source bytes. This is identity evidence, not scanning source as behavior proof.
uv.lock changes only product 0.3.0 -> 0.4.0; no dependency added/upgraded.
The ZIP retains wheel, locked runtime requirements, both new workspaces including
empty directories, content, script, receipts and stdout. Per-file hashes are in
retained-trial-manifest.json. Extraction into a new empty temporary directory was
checked with six installed read/inspect/status commands without changing either DB:
backup-check.json. This is local backup verification, not independent external install.

Commands and actual evidence, relative to this worktree:

| Command | Observed result | Raw evidence under docs/work4/evidence/ |
|---|---|---|
| uv sync --locked | Managed environment prepared; version-only refresh reused 24 locked packages | Tool transcript; preparation notes in cost |
| uv run --locked python -m tools.check, accepted basis | PASS, 51 tests, native hygiene/types/2 boundaries/build | baseline-check.txt |
| uv run --locked python -m tools.check, implementation | PASS, 74 tests, native hygiene/types/2 boundaries, wheel/sdist | development-check.txt |
| uv run --locked python -m tools.probe_artifacts --accepted-trial C:/Users/Anton/AppData/Local/Temp/zaratustra-work3-gnt5ksg0 | exit 0; exact outside-checkout 0.4.0, real console, copied v3 -> v4, versions/read/repair and installed DB/rebuild faults | install-artifacts.txt; installed-manifest.json; installed-receipt.json; terminal-session.json |
| uv run --locked python -m tools.probe_install | exit 0; current-wheel init/status/re-init, same bootstrap DB bytes | install-bootstrap.txt |
| uv run --locked python -m tools.probe_records --accepted-trial C:/Users/Anton/AppData/Local/Temp/solmax-work1-accept-20260907-a1/retained-trial | exit 0; current wheel, copied v1 -> explicit schema 2, initial records/restarts, original preserved | install-records.txt |
| uv run --locked python -m tools.check --deliver | PASS / exit 0: 74 tests, native hygiene/types/2 boundaries/build and report presence; presence does not establish acceptance truth | deliver.txt |

Focused 69- and 72-test runs are developmental feedback, not delivery evidence.
The final 74 comprise 51 retained baseline cases and 23 new cases. Old mutation
tests and probe_mutations explicitly select schema 3; the unsupported-schema
fixture moved 4 -> 5. Their behavior assertions remain. Released migrations,
validation.config and REVIEW.md are unchanged. No skip/xfail, owner-visible wording
or tuning tests, and no source scanning substitute for runtime behavior.

Main trial starts from the exact Work 3 revision 4 and three old events/receipts.
Original quartet ids/creation values remain:

workspace_id: 4846e59f-b3f8-4ed1-9bb3-fea22f713b88
Process: bae978a9-a181-4368-be55-b1837fd47747
Work: 56785bef-c147-4236-b12a-cad24845567a
Artifact: ae7eca56-fd16-41ad-b262-2981468b922e
initial Event: b0257ea3-6179-4ac2-95a2-de033bf98078

| New operation | operation_id | Event | Global revision |
|---|---|---|---|
| authorize_work | d046b21b-e0ad-45f1-81a3-182228e55542 | e64623ab-dd89-49ee-a6e2-687f59ae8985 | 4 -> 5 |
| authorize_artifact | ced01bc2-04df-4b90-b3e5-b868438fb7dd | d830012f-9c6d-491b-aff4-947d1efabbf8 | 5 -> 6 |
| publish_artifact, first version | 258ea271-3f06-4c29-9caa-09cf2613d2d4 | ab042f0e-7aa9-45c2-b7d1-e0b5fceb8493 | 6 -> 7 |
| publish_artifact, second version | 75a8c7b3-3f17-4a50-a777-c70f3515bfd8 | 5519b7cc-95ae-4246-9ecf-3187dbf5969f | 7 -> 8 |
| restore_artifact, exact second version | b4e35da8-b5e5-4bfc-9b2b-b9a1891b482a | a488c867-6880-4479-8b94-71af64943b0c | 8 -> 9 |

Version ids equal publication operation ids. First content: 59 bytes, SHA-256
de22a67833d4525f95d460d75890f8a046a08d51e19bd086e380df104afd1214.
Second active content: 68 bytes, SHA-256
6fd73651c03ddf966703c5b96f6b7a7da79a6d3482b82342f191dd4ea9299b45.
Files: artifacts/<Artifact-id>/<version-id>.blob. Work/global revision=9,
status=ready, scope=work_metadata_and_artifact. Artifact revision=3, two versions,
eight total mutation events/receipts. Initial Event remains revision 1/version 0.2.0;
Process and immutable original metadata remain unchanged.

On the second new copy, a real SQLite authorizer rejects COMMIT after complete file
publication. DB hash stays unchanged; the file remains unregistered. Same-id retry
checks/reuses it, commits once, then an injected projection I/O failure returns
durable receipt 35f62fde-6519-478f-8dd9-2ec0c47b5c53, event
05a17be7-bcc0-4c28-a729-cca4e420def2, revision 9 -> 10. CLI rebuild changes no DB
bytes and content reads correctly. No manual SQL/state Markdown produced success.
Native tests separately exercise CLI exit 2 and its exact committed receipt.

Five main-trial approvals were entered by the executor under this fictional CALL
using real stdin/stderr terminal handles. terminal-session.json retains raw prompts,
executor inputs and terminal controls; install-artifacts.txt retains subprocess
stdout, noninteractive stderr and exits. The fault copy uses the explicitly labeled
local-chat/executor-fictional-trial adapter. These are not owner identity/runtime PASS.

All 24 named accepted DB/wheel/receipt/evidence files from 0.1/0.2/0.3 and fresh G5
match the committed manifests before/after: preserved-before.json and preserved-after.json.
The old 0.3 trial remains C:/Users/Anton/AppData/Local/Temp/zaratustra-work3-gnt5ksg0;
DB hash remains 8c42aab9da01d270ff8a054122e2ae9bbe004cd70ab66b10927961e85c5409ea;
wheel remains 860804660548cd20bbd976f96bf5d27fe21855a56406b5bc7c7dcbe0ab08c1f2.
Those manifests list every earlier locator/hash. No original was migrated.
Final delivery rebuilt the same wheel SHA-256. Walkthrough commands were rerun
against the retained main trial: current revision 9, both versions verified, active
note readable, DB hash unchanged. Raw outputs: walkthrough.txt,
walkthrough-overview.txt and walkthrough-history.json. These remain executor reads.
Committed Direction source locators/hashes: sources.json. No Direction write occurred.

## assumptions

The accepted architecture hash
4f90d19fc742ab616301b6b4121880f76c75faaeb1f606c8190a84853d8b3e0e,
current CALL, PROBA v36 and W21 owner words govern this slice. Existing delegation
permits the PLAN's conforming HOW; it does not supply a new owner runtime verdict.

Single-owner console access and genuinely trusted local-chat application code remain
the trust boundary. No accounts, identity proof, secret store or hostile same-user
isolation. New scope is limited to the sole Artifact of this Work/Process; payload
cannot grant it. Receipt reads still require current metadata rights. Owner-local
records/history/artifact/projection reads are filesystem-owner inspection, not
Work context isolation. Future importer/context must bind their actual caller.

File publication and SQLite COMMIT are separate. A complete uncommitted file can
remain orphaned. Missing/changed committed bytes cause read refusal, never fallback;
receipt does not prove present availability. Exact restore retains damaged bytes
and gets a new audited repair effect without switching active version/descriptor.
Failed repair may leave restored physical bytes or quarantine while DB is unchanged;
retry revalidates them. There is no atomic filesystem/DB rollback promise.

Files use fsync and SQLite uses synchronous FULL. Measured failures are local I/O,
statement/commit rejection, interrupted repair, lost reply, concurrency and rebuild.
Process-kill/hot-journal recovery, power/disk/controller loss and hostile path races
are not demonstrated. No automatic cleanup, background recovery, downgrade or
arbitrary DB repair. Any broader consumer guarantee must be decided before reliance.

generated_at uses the retained source-event timestamp (initial/workspace creation
when appropriate), yielding identical rebuild bytes. Projection status compares
DB-derived content, never trusts a Markdown header. Serialized rebuild reads latest
DB state; metadata/history remain inspectable after loss of content/generated
directories in schema 4. Projections do not assert current content availability.

## cuts

No Work 4 done_when removed. One Artifact lifecycle and one owner-local overview
extend the existing single graph. No second full/real Process, permanent personal
workspace, Handoff file/stdin, Work context, submit_result/next Work, memory system,
MCP, clean-chat proof or full Work 8 demo. Works 5–8/M1+ have not started; T3/M0
closure and successor CALLs belong to Direction and are not produced here.

Both owner-ack:solmax-zaratustra-work1-no-automation-20260907 and
owner-ack:solmax-zaratustra-local-setup-no-automation-20260907 remain operative.
No CI/CD/Actions/notifications/setup/test push, Product remote/account/publication,
new cost/external right, real personal data, independent external install/upgrade,
full move, Direction OS/old-repository write or Direction archive read.

| ID | Work 4 disposition | Remaining answerer / point / rewrites |
|---|---|---|
| W19 | Literal order, current rights, original stale conflict, refreshed receipt, collision and terminal refusal preserved. | PLAN before Works 5/7: importer and Result/next unit; rewrites importer/receipts/linkage/tests/migrations; cheap reversal unproved. |
| W20 | File-before-DB, orphan/retry, exact repair, committed receipt/rebuild and late-availability refusal measured in stated model. | PLAN before Work 7 continuation or broader recovery/durability; rewrites durable references/recovery/evidence/migrations. |
| W21 | Exact local channel, narrow Artifact scope, content digest/size binding, revoked/terminal refusal. | PLAN before Works 5/6/7 actual importer/context; rewrites adapters/permissions; decision is not runtime acceptance. |
| W22 | Global/Work plus Artifact revisions, exact id/version/hash references, coherent snapshot. | PLAN before Work 6 scope/freshness/budget/delivered manifest and later decision/membership dependencies; rewrites snapshot/context/tests; no duty cut. |
| W23 | No clean-chat proof. | PLAN before Works 6/8, exact input and real separate response on five facts in Work 8; rewrites delivery/demo; unprovable cleanliness blocks. |
| W24 | Explicit v4/request v2, v1 canonical compatibility, no-replace publication, SHA-256, quarantine/rebuild. | PLAN before later cleanup/recovery consumers; rewrites mechanics/tests/migrations; semantics return W19–W22. |
| W25 | New copies of one fictional graph, foreign id/hash/path/refusal and missing-content fixtures; not context isolation. | PLAN before Works 5/6/8 negative context fixture; rewrites fixtures/tests/demo; no second full Process. |
| W26 | Actual isolated path/base/branch/no remote, exact installed 0.4, preserved 0.1/0.2/0.3/G5 artifacts. | PLAN before permanent folder/hosting/independent external install-upgrade; rewrites package/layout/docs; reassess with external consumers. |
| W27 | Public Core metadata/receipt/verified-content/inspection/rebuild seams for E1/E2/E3/E6/E8/E9/E10/E11. | PLAN at each consumer admission; rewrites Core/data/consumer migrations; E4/E5/E7/E12 no invented API, M1+ no prerequisite; cheap replacement unproved. |

## cost

One executor and the one bounded read-only setup evaluator required by AGENTS;
no implementation/review subagents. Setup checked initial base/no remote, PROBA 36,
hook and tool availability, and ran no behavior checks. It is not binding G5.
Parent performed all mutations and native/installed checks.

Approximately 35–50 minutes after committed admission for implementation/check/report,
plus preparation and waiting for Direction's atomic transition; estimate, not billing
or deadline. This fits the focused half-day calibration. Existing tools/subscriptions
only; no new dependency/service/spend. Exact token/account cost unavailable.

Initial uv-cache and shared Git metadata access required approved sandbox escalation.
An own PowerShell replacement mistake affected five target files and was repaired
from the exact clean base plus intended replacements before checks/commit. Focused
mypy feedback found import/variable typing and probe monkeypatch assignment issues;
fixed before full verification. A report patch was rejected as invalid before any
write and reapplied correctly. Full baseline/implementation gates passed their first
full runs; installed probes passed. No gate exhausted three retries; no required
tool, owner choice, scope divergence or auto-approval rejection remains blocked.

## manual-acceptance

W21 words remain in docs/work3/OWNER-DECISION-20260908.md. Owner continuation and
plan-conforming delegation admit this Work; they are not substituted for runtime
testing. Owner Work 4 runtime acceptance: not performed/inferred. Binding fresh G5
for exact Work 4: not performed here. Full owner demonstration remains after Work 8.

Walkthrough: docs/work4/INSTALL.md contains exact paths and PowerShell commands for
version/state, both content hashes, decoded active note, overview and history.
Main retained state: Work/global revision 9, Artifact revision 3, two verified
versions and quarantined negative-fixture bytes. The commands are owner-local reads.
Keep the retained sample fixed; a new probe makes a fresh copy. No DB/state Markdown
hand edit forms part of the walkthrough or recovery. Any owner stdout is separate
from executor evidence and is not automatically inferred as acceptance.

## next

next: solmax
HOME: evaluate all three Work 4 done_when against implementation
2100775adfd78ad83a3ff615f9d9e4eeec32eb5b, exact wheel/hash, full native/installed raw
evidence, declared file/DB boundary and W19–W27. T3 close route remains binding
fresh physical G5 of this exact version. Old Work 3 G5 supports matching old claims,
not Work 4 file guarantees. Product issues no CALL, closes no T3/M0 and starts no Work 5.

END_OF_FILE: RESULT.md
