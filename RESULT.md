# Product RESULT — Zaratustra setup

call: c-solmax-zaratustra-m0-bootstrap-20260907-setup
engineering_contract: 36
mode: PROBA
repo: C:/projects/zaratustra
direction: solmax

## outcome
LOCAL_SETUP_READY / ESCALATE external checklist disposition.
New local Git repository contains a tested installable development scaffold
and the applicable PROBA v36 contract. CI and notification push remain unperformed,
not silently accepted or cut. Owner acceptance has not been received.
Work 1–8 remain unimplemented; T1 and M0 are not closed.

## evidence
1. CALL done_when 1: local repo, managed Python 3.13.7, installed stamp 36/PROBA,
   concise root/module contracts, packaging and every checklist disposition:
   docs/setup/SETUP.md, validation.config, docs/setup/evidence/repository-facts.txt.
   Full checklist completion is UNPROVEN while CI and test-push dispositions are pending.
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
CI and external notification/test push are unresolved, not approved cuts.
Actual user installation/init stays Work 1. External independent install, M1+,
MCP, real Process, migration from old repos, publishing and expenses remain outside
this CALL. No archives, old product repos or live Direction state were modified.

## cost
One setup-only root, one bounded read-only evaluator smoke. No API purchase,
paid runner, external service or publishing charge was initiated.
Initial local gate run failed once on output decoding; corrected run passed.
Token cost is not available as a task-specific measured amount.
Elapsed wall time is recorded in the completion receipt; it is not an appetite
threshold or a new delivery deadline.

## manual-acceptance
Pending. The owner asked only to run the setup CALL; no later acceptance words exist.
The executor's build/install checks prove only local setup facts.
Decision owed: accept local setup with CI/test-push deferred to a separately
authorized service choice, or select those services and authorize their test now.
Recommendation: local setup first. Detailed ready result: docs/setup/SETUP.md.
Do not promote this report into a Direction close or into evidence of the M0 demo.

## next
solmax
HOME evidence for the next Direction work session. Keep the registered setup CALL,
T1 and M0 open until the authorized Direction session resolves this report and
the pending owner disposition. It alone issues a subsequent local admission.
W19–W27 stay open (docs/setup/OPEN-AGENDA.md); W26 has setup packaging evidence,
but actual user install/layout is not complete. No Work 1 launch authority here.

END_OF_FILE: RESULT.md
