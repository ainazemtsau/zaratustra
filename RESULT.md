# Product RESULT — Zaratustra setup

call: c-solmax-zaratustra-m0-bootstrap-20260907-setup
engineering_contract: 36
mode: PROBA
repo: C:/projects/zaratustra
direction: solmax

## outcome
LOCAL_SETUP_COMPLETE / REPORT HOME.
New local Git repository contains a tested installable development scaffold
and the applicable PROBA v36 contract. The owner accepted the local scope by
explicitly removing CI/CD, Actions and push requirements until a separate request.
Receipt: docs/setup/OWNER-DECISION-20260907.md.
No external run or owner-performed runtime check is claimed.
Work 1–8 remain unimplemented; T1 and M0 are not closed.

## evidence
Exact source/setup commit: e74bda8aa4a38fab8559ed8ebfab73e0f6135f7f.
First commit diff: 48 files / 1901 insertions, including lock and raw evidence.
Receipt and measured local elapsed: docs/setup/LOCAL-RECEIPT.md.
1. CALL done_when 1: local repo, managed Python 3.13.7, installed stamp 36/PROBA,
   concise root/module contracts, packaging and every checklist disposition:
   docs/setup/SETUP.md, validation.config, docs/setup/evidence/repository-facts.txt.
   PASS within the owner-approved local scope: CI and test-push are explicitly cut,
   not claimed executed. Owner-ack:solmax-zaratustra-local-setup-no-automation-20260907.
2. CALL done_when 2: uv sync --locked; full and file-scoped checks; wheel/sdist
   build; isolated wheel install/import outside checkout. Raw outputs under
   docs/setup/evidence/: dependency-install.txt, check-final.txt,
   file-scoped-check.txt, boundary-negative.txt, install-probe.txt, environment.txt.
   Real source boundary violation fails; local commit rejects scratch seed.
   Initial Windows decoding failure is preserved and fixed, not hidden.
3. CALL done_when 3: this report plus docs/setup/OPEN-AGENDA.md preserves W19–W27,
   evidence, assumptions, cuts, cost, manual-acceptance and HOME. No Direction
   continuation is issued by this executor. Full checklist and first-commit receipt
   are recorded with this handback.

Scope: packaging metadata/lock; 3 empty module __init__.py files; module docs;
development check + isolated-install runner; setup-gate tests; local Python
Git hygiene hook; repo-only agent configuration; OpenSpec document folders;
source provenance, copied CALL, evidence and this report.
Optional stack/packaging decision record: docs/adr/ADR-0001.md.
Evaluator: docs/setup/evidence/evaluator-smoke.txt — same-session smoke only,
not binding fresh G5, independent review or product acceptance.
state_changes (Direction OS): none.
Proposed Python-profile delta: docs/setup/python-profile-proposal.patch;
proposal only, requires the owning workflow writer/maintenance route.

## assumptions
Setup-only admission permits reversible local scaffold/packaging choices.
One packaged src/zaratustra root with Core/CLI matches accepted §§26–27/41.
uv_build 0.8.22 matches observed uv 0.8.22; toolchain == pins and uv.lock preserve
the versions resolved here. mutation_kill_floor=80 is a dormant configuration
default, never evidence that OPORA or mutation is enabled.
No owner-approved public license, external account, user workspace or runtime
on another operating system has been inferred.

## cuts
No product acceptance item or Work was implemented or declared complete.
PROBA-exempt gates are named N/A with source in docs/setup/SETUP.md.
CI/CD, GitHub Actions and push notifications (including their setup/test push)
are owner-approved cuts until a separate owner request. Exact response and scope:
docs/setup/OWNER-DECISION-20260907.md. Their absence is no longer a blocker.
Public GitHub hosting remains future work; it was not cancelled or configured.
Actual user installation/init stays Work 1. External independent install, M1+,
MCP, real Process, migration from old repos, publishing and expenses remain outside
this CALL. No archives, old product repos or live Direction state were modified.

## cost
One setup-only root, one bounded read-only evaluator smoke. No API purchase,
paid runner, external service or publishing charge was initiated.
Initial local gate run failed once on output decoding; corrected run passed.
Token cost is not available as a task-specific measured amount.
Elapsed wall time since repo creation is recorded in docs/setup/LOCAL-RECEIPT.md; it is not an appetite
threshold or a new delivery deadline.

## manual-acceptance
Local scope accepted by the owner's response to the setup-acceptance question:
«Пока я отдельно об этом не скажу, можно вырезать это требование.»
Exact full response: docs/setup/OWNER-DECISION-20260907.md;
owner-ack:solmax-zaratustra-local-setup-no-automation-20260907.
The executor's build/install checks still prove only local setup facts.
No owner-performed runtime test or M0 demo is inferred.
This product REPORT is evidence for Direction, not itself a Direction close.

## next
solmax
HOME evidence for the next Direction work session, now with the external
scope decision resolved. The authorized Direction session may consume this
setup report under its own checks and issue the subsequent local admission.
The executor does not edit or close Direction CALL/T1/M0 state.
W19–W27 stay open (docs/setup/OPEN-AGENDA.md); W26 has setup packaging evidence,
but actual user install/layout is not complete. No Work 1 launch authority here.

END_OF_FILE: RESULT.md
