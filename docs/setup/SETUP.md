# Zaratustra setup applicability — 2026-09-07

Outcome: LOCAL SETUP READY; external checklist items unresolved.
Product: C:/projects/zaratustra. CALL: docs/setup/CALL.md.
Installed surface: contract v36 / PROBA only. OPORA is not enabled.
This report does not close the Direction CALL, T1, M0, or any Work 1–8.

Authority: Direction OS commit 397e8dd1bce4fa59bd0d9e8f0be08ad4849eb58a,
os/engineering/PROJECT_SETUP.md plus CONTOUR.md §Two modes and profiles/python.md.
CALL source basis 638a12a815880e6f9c01cbeff155b74f92b26001 remains provenance.
Source digests and checklist ordering are in source-provenance.txt.

PROBA explicitly exempts pair/freeze, independent test-author/refutation, stage
receipts/manifests, replacement lineage, ADR, mutation, negative controls,
property audit and review artifacts. Those gates are not claimed enabled.
The small stack/packaging record is optional documentation, not an ADR gate.
Completion still requires the owner's words. A green local command is not that verdict.

## Checklist disposition

Row numbers match the 30 top-level Done-when items in the referenced PROJECT_SETUP.
PASS below means the named local setup fact was observed; it does not mean product acceptance.

| # | Checklist item | Disposition and evidence |
|---|---|---|
| 1 | Compiled carrier/RED pair contract | N/A PROBA, CONTOUR §Two modes; no frozen carrier/tests. OPORA STOP in AGENTS. |
| 2 | One command locally and in CI | LOCAL PASS: evidence/check-final.txt. CI NOT RUN: no remote repo/provider/rights selected; owner disposition pending. |
| 3 | Dependency boundary seeded violation | PASS: real import-linter, 2 kept clean / 2 broken on reverse import; evidence/boundary-negative.txt. |
| 4 | Root ≤150 lines; module docs | PASS: AGENTS.md and each package/Core/CLI AGENTS.md; evidence/repository-facts.txt. |
| 5 | Run contract | PASS, mode-translated: 10 numbered lines in root AGENTS; heavy clauses N/A per PROBA. |
| 6 | Repo-local execution authority | PASS: AGENTS run contract 1–2 and 5, evaluator smoke. |
| 7 | Report/home plus heavy evidence gates | Report fields and HOME installed in AGENTS/validation.config; field-presence runner tested. Heavy clauses N/A PROBA; no fabricated evidence. |
| 8 | v30 stage-root routing/replacement | N/A PROBA: no stage receipts or replacement lineage owed. Report returns HOME. |
| 9 | v31/v34 lifecycle seeded misses | N/A PROBA; stage/lifecycle gates not installed or claimed. |
| 10 | Missing/incomplete RESULT rejects deliver | PASS: test_report_presence_and_config_fields; final --deliver command. |
| 11 | Cited local artifact existence | PASS: test_citation_absent_present_and_omitted; always checked, even outside --deliver. Presence only. |
| 12 | Mutation floor configured | PASS presence: 80 and mutation_runner=none. Dormant default, no mutation PASS or OPORA sufficiency claim. |
| 13 | Installed contract stamp | PASS: validation.config synced_contract_version=36, supported_modes only PROBA. |
| 14 | Strong-check evidence seeded misses | N/A PROBA: no mutation/spec-silence/frozen-spec deliver gate installed. |
| 15 | Review-evidence gate | N/A PROBA: no review artifact gate or independent review claimed. |
| 16 | Refuted-register gate | N/A PROBA: no review findings/refutations are being closed. |
| 17 | Fix-class-closure gate | N/A PROBA: no heavy review/sweep gate installed. |
| 18 | Acceptance negative-control gate | N/A PROBA; setup gate seeds are hygiene/presence mechanics, not frozen product oracles. |
| 19 | Property-layer gate | N/A PROBA; no Core algorithm implemented. |
| 20 | Frozen-spec deliverable coverage gate | N/A PROBA: no frozen spec. CALL's 3 done_when are dispositioned in RESULT instead. |
| 21 | Mutation runner and authoritative scope | N/A PROBA; mutation_runner=none. |
| 22 | Mutation scope seeded misses | N/A PROBA; no scope/score claims. |
| 23 | Mutation diff identity | N/A PROBA; no mutation artifacts. |
| 24 | Mutation dirty-input rejection | N/A PROBA; no mutation runner. |
| 25 | Contract files/OpenSpec | PASS: REVIEW.md, validation.config, docs/adr/ADR-0001.md, docs/FRICTION.md, openspec/. Native documents only. |
| 26 | Stack profile feedback | Existing Python profile used; exact proposed delta in python-profile-proposal.patch. Workflow sources untouched; proposal unaccepted. |
| 27 | Scratch seed cannot commit normally | PASS: ignored seed; forced-stage seed rejected by actual Python Git hook. Tests include both. Hook enabled locally through core.hooksPath. |
| 28 | Test hygiene seeded misses | PASS: outside tests, missing source, skipped/xfail/aliased skip, assertion-free, non-portable literal, clean control. |
| 29 | Notification hook test push | NOT INSTALLED / NOT RUN. No selected push channel or external messaging authorization. Pending owner disposition; not a PROBA exemption. |
| 30 | Read-only evaluator smoke | PASS in bounded sense: same-session prompt-injected evaluator answered by read-only actions; evidence/evaluator-smoke.txt. Auto-discovery/enforced isolation not claimed. |

## Other setup steps and limits

- Step 1: accepted stack reused without a repeated interview; compatible packaging
  selected within setup. Exact comparison in ADR-0001; no new owner words invented.
- Step 2: one package, only Core/CLI modules; real layer/forbidden graph contracts.
  Future modules must be added explicitly to the graph and get local docs.
- Step 3: native commands, nearest-module docs, concise PROBA run contract,
  constitution, rubric, validation.config and friction installed.
- Step 4: uv lock and managed Python; report/hygiene/native gates enabled.
  CI and push are unresolved external checklist items, not silently cut.
  Python Git hook blocks tracked scratch under normal commits; bypassing hooks
  remains technically possible and prohibited by the repo contract.
  STOP/STEER convention is local and not an OS-wide interrupt.
  No new globally installed skill or tool requirement.
- Step 5: first Git commit records setup. No SPEC/ledger/PROGRESS stage machinery
  is owed in PROBA. tasks.md completion gates are forbidden in either mode.
- C# compiler/public-carrier/Unity sidecar examples are inapplicable to this Python
  setup and do not authorize a surrogate compiler pipeline.
- Windows is the observed platform. No Linux/macOS/CI run, owner trial, real
  workspace selection, external independent-install proof, public license choice,
  remote repository creation, publication, paid runtime or API call is claimed.
- OpenSpec here is its native document surface, not an installed Node CLI.
- A read-only helper smoke does not discharge fresh Direction G5 for a later task close.

## Installation observation

uv builds wheel + sdist. tools/probe_install.py creates an isolated managed
Python 3.13.7 environment under a checked system temporary root, installs the
wheel plus locked runtime dependencies, checks compatibility, then imports
Core/CLI under Python -I from an empty directory. It confirms site-packages
outside this checkout, Pydantic v2, sqlite3 and SHA-256, with the cwd still empty.
The temporary environment is cleaned after proof. No persistent user workspace
is chosen. Raw output: evidence/install-probe.txt.
This proves the scaffold can be packaged, not Work 1 installation/init.

## Unresolved external decision

Recommend accepting this as local setup and deferring CI and external push until
a separate authorized service choice. Neither is marked PASS.
PROJECT_SETUP Done-when #2 requires local+CI, #29 requires a test push.
The CALL forbids new external rights/publication/accounts/cost without owner words;
profiles/python.md also makes CI deployment an owner decision.
If the owner requires those items now, the exact provider/channel and permission
must be named before configuration or a test message. No external operation was attempted.

END_OF_FILE: docs/setup/SETUP.md
