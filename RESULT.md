# Stage 3 — web discussions and incoming requests

## outcome

Candidate 0.21.0 implements the owner's September17 approved scope over published
0.20.0 a3e1c970bee97ef73c49084c1b940665d4bed4db: selected web discussion material,
GitHub handoffs, tolerant original capture, recoverable item/attachment processing
through ordinary Pi and fresh-chat continuation. See docs/stage3/IMPLEMENTATION.md.
The prior report is retained in docs/results/2026-09-16-stage2b-skills.md.

## evidence

Full native delivery gate: PASS, 485 tests, 26 import contracts, formatting/lint,
strict types, hygiene, build and report structure. The focused web suite has 12
tests. The installed candidate wheel was exercised by ordinary Pi in fresh chats
in a fictional Home: proposal saved, missing report requested, supplied file
preserved byte-for-byte, request completed, sources reopened in another new chat.
Independent public-API checks verify one completed request, zero pending and equal
original/saved report hashes. See docs/stage3/VERIFICATION.md and its retained
evidence; docs/stage3/USER-WALKTHROUGH.md shows the ordinary user path.

An in-session read-only evaluator found issues in attachment accounting, source
freshness, recovery, later authority and branch instructions. Corrections and
behavioral regressions were added. This is not binding Direction G5 or owner
acceptance. The legacy catalog concurrency observation remains OPEN and UNFIXED;
see docs/stage2b/OPEN-OBSERVATIONS.md and its original retained trace.

## assumptions

The trusted local-owner boundary remains. Agents interpret actual instructions and
semantic conflicts; code validates bytes, schemas, scope, references, revisions and
known delivery accounting. GitHub uses existing gh authentication. Instructions do
not grant ChatGPT a missing write tool.

## cuts

No automatic model routing, provider execution, new subscription, background work,
automatic attachment retrieval, private installation update or Stage4. Only selected
text files are published. The real personal ChatGPT/GitHub transfer is a separate
visible hookup step; local and fake transport checks do not establish that capability.

## cost

One implementation agent, one bounded read-only setup/review helper, existing
Python/uv tools and installed Pi for fictional verification. No new service or
dependency. No personal Home data authored or changed.

## manual-acceptance

Scope approved by the owner's «ок». Acceptance of delivered behavior is pending
the demonstration and owner's verdict. Full development migration is not claimed.

## next

solmax — show actual checks and limitations, then one explicit personal hookup step.
Do not automatically start another stage or change the owner's installation.

END_OF_FILE: RESULT.md
